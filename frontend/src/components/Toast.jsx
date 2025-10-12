export default function Toast({msg}){
if (!msg) return null
return <div className="toast">{msg}</div>
}