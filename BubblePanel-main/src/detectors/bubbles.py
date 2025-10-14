from typing import List, Tuple
import cv2, numpy as np

# ---------- utilities ----------
def _local_variance(gray: np.ndarray, k: int) -> np.ndarray:
    f = gray.astype(np.float32)
    m = cv2.blur(f, (k, k))
    m2 = cv2.blur(f * f, (k, k))
    return np.clip(m2 - m * m, 0, None)

def _nms_xyxy(boxes_xyxy, iou_thresh=0.3):
    if not boxes_xyxy: return []
    b = np.array(boxes_xyxy, dtype=float)
    a = (b[:,2]-b[:,0]+1)*(b[:,3]-b[:,1]+1)
    order = np.argsort(a)[::-1]; keep=[]
    while order.size>0:
        i=order[0]; keep.append(i)
        xx1=np.maximum(b[i,0],b[order[1:],0]); yy1=np.maximum(b[i,1],b[order[1:],1])
        xx2=np.minimum(b[i,2],b[order[1:],2]); yy2=np.minimum(b[i,3],b[order[1:],3])
        w=np.maximum(0,xx2-xx1+1); h=np.maximum(0,yy2-yy1+1)
        inter=w*h; iou=inter/(a[i]+a[order[1:]]-inter+1e-6)
        order=order[np.where(iou<=iou_thresh)[0]+1]
    out=[]; 
    for i in keep:
        x1,y1,x2,y2 = b[i].astype(int).tolist()
        out.append((x1,y1,x2-x1,y2-y1))
    return out

def nms_boxes(boxes, iou_thresh=0.3):
    xyxy=[(x,y,x+w,y+h) for (x,y,w,h) in boxes]
    return _nms_xyxy(xyxy, iou_thresh)

# ---------- grow constrained by edges + whiteness ----------
def _edge_constrained_grow(seeds, white, edge, grow_px, iters, roi):
    x1,y1,x2,y2 = roi
    x1=max(0,x1); y1=max(0,y1)
    S = (slice(y1,y2), slice(x1,x2))
    region = (seeds[S]>0).astype(np.uint8)*255
    if np.count_nonzero(region)==0: 
        return None
    W = (white[S]>0).astype(np.uint8)*255
    B = (edge[S]>0).astype(np.uint8)*255  # barrier

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(grow_px,grow_px))
    for _ in range(max(1,iters)):
        prev = region.copy()
        region = cv2.dilate(region,k,1)
        region = cv2.bitwise_and(region,W)
        region = cv2.bitwise_and(region, cv2.bitwise_not(B))
        if np.array_equal(prev,region):
            break

    num,_,stats,_ = cv2.connectedComponentsWithStats(region,8)
    if num<=1: return None
    idx = 1 + int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    rx,ry,rw,rh = [int(stats[idx,j]) for j in (cv2.CC_STAT_LEFT,cv2.CC_STAT_TOP,cv2.CC_STAT_WIDTH,cv2.CC_STAT_HEIGHT)]
    return (x1+rx, y1+ry, x1+rx+rw, y1+ry+rh)

# ---------- main ----------
def detect_bubbles_in_panel(bgr, panel_box, cfg) -> List[Tuple[int,int,int,int]]:
    x0,y0,w0,h0 = panel_box
    roi = bgr[y0:y0+h0, x0:x0+w0]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    H,W = gray.shape[:2]

    # scale to panel size
    base = 1024.0
    s = max(0.6, min(2.5, max(H,W)/base))

    # config
    merge_px   = int(round(cfg.get("text_group_merge_px",58)*s))
    expand     = int(round(cfg.get("bubble_expand_px",20)*s))
    vw         = int(round(cfg.get("var_window",9)*s)); vw = vw if vw%2==1 else vw+1
    white_pct  = int(cfg.get("white_percentile",83))
    var_pct    = float(cfg.get("var_percentile",42))
    min_wr     = float(cfg.get("min_white_ratio",0.52))
    iters      = int(cfg.get("grow_iters",24))
    min_area   = int(cfg.get("bubble_min_area",220))
    max_area   = int(cfg.get("bubble_max_area",500000))
    max_aspect = float(cfg.get("bubble_max_aspect",4.6))
    min_sol    = float(cfg.get("bubble_min_solidity",0.50))

    # priors
    white_thr = np.percentile(gray, white_pct)
    white = (gray >= white_thr).astype(np.uint8)*255
    var = _local_variance(gray, vw)
    var_thr = np.percentile(var, var_pct)
    smooth = (var <= var_thr).astype(np.uint8)*255
    prior = cv2.bitwise_and(white, smooth)

    # edges (balloon rim)
    edge = cv2.Canny(gray, 70, 160)
    edge = cv2.dilate(edge, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),1)

    # --- multi-contrast maps to pop text ---
    ksz = max(9, int(15*s))
    K = cv2.getStructuringElement(cv2.MORPH_RECT,(ksz,ksz))
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, K)   # bright-on-dark
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, K)# dark-on-bright
    inv_top = 255 - tophat
    inv_blk = 255 - blackhat

    # --- multi-scale MSER seeding (small + large letters) ---
    def mser_boxes(img, amin, amax, delta):
        try:
            m = cv2.MSER_create(); m.setDelta(delta); m.setMinArea(amin); m.setMaxArea(amax)
        except Exception:
            m = cv2.MSER_create(delta, amin, amax)
        regs,_ = m.detectRegions(img)
        return [cv2.boundingRect(r.reshape(-1,1,2)) for r in regs]

    amin_base = int(round(cfg.get("mser_min_area",18)*(s**2)))
    amax_base = int(round(cfg.get("mser_max_area",20000)*(s**2)))
    small = mser_boxes(inv_blk, max(8, int(0.5*amin_base)), int(0.4*amax_base), int(cfg.get("mser_delta",5)))
    large = mser_boxes(inv_top, int(0.3*amax_base), amax_base, int(cfg.get("mser_delta",5)))

    seeds = np.zeros_like(gray, dtype=np.uint8)
    for x,y,w,h in small+large:
        cv2.rectangle(seeds,(x,y),(x+w,y+h),255,-1)

    # group seeds so each cluster ≈ one bubble
    grouped = cv2.dilate(seeds, cv2.getStructuringElement(cv2.MORPH_RECT,(merge_px,merge_px)),1)

    # grow each cluster within a local window
    cand_xyxy=[]
    num,_,stats,_ = cv2.connectedComponentsWithStats(grouped,8)
    for i in range(1,num):
        x,y,w,h = [int(stats[i,j]) for j in (cv2.CC_STAT_LEFT,cv2.CC_STAT_TOP,cv2.CC_STAT_WIDTH,cv2.CC_STAT_HEIGHT)]
        if w*h < min_area or w*h > max_area: continue
        if max(w/max(h,1), h/max(w,1)) > max_aspect: continue

        x1=max(0,x-expand); y1=max(0,y-expand)
        x2=min(W,x+w+expand); y2=min(H,y+h+expand)

        grown = _edge_constrained_grow(seeds, prior, edge, max(5,int(5*s)), iters, (x1,y1,x2,y2))
        if grown is None: 
            continue
        gx1,gy1,gx2,gy2 = grown
        wr = float(np.count_nonzero(prior[gy1:gy2, gx1:gx2])) / ((gx2-gx1)*(gy2-gy1)+1e-6)
        if wr < min_wr: 
            continue
        cand_xyxy.append((gx1,gy1,gx2,gy2))

    # fallback: outline-only (rarely needed now)
    if not cand_xyxy:
        e = cv2.Canny(gray, 60, 150)
        e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)),1)
        cnts,_ = cv2.findContours(e, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x,y,w,h = cv2.boundingRect(c)
            if w*h < min_area or w*h > max_area: continue
            hull = cv2.convexHull(c)
            sol = (cv2.contourArea(c)+1e-6)/(cv2.contourArea(hull)+1e-6)
            if sol < min_sol: continue
            if float(np.mean(gray[y:y+h, x:x+w])) < np.percentile(gray, 70):
                continue
            cand_xyxy.append((x,y,x+w,y+h))

    # map to full coords + nms
    cand_xyxy = [(x0+x1, y0+y1, x0+x2, y0+y2) for (x1,y1,x2,y2) in cand_xyxy]
    return _nms_xyxy(cand_xyxy, iou_thresh=0.30)
