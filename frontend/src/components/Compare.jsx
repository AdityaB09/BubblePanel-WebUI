export default function Compare({left, right}){
if (!left || !right) return null
return (
<div className="card vstack">
<div className="title">Compare Runs</div>
<div className="row">
<pre style={{whiteSpace:'pre-wrap'}}>{left.stdout}</pre>
<pre style={{whiteSpace:'pre-wrap'}}>{right.stdout}</pre>
</div>
</div>
)
}