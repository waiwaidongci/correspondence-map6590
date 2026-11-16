import type {IntervalConflict} from '../types/domain';
export function IntervalConflicts({conflicts}:{conflicts?:IntervalConflict[]}){
 if(!conflicts?.length)return null;
 return <section className="interval-conflicts">
  <header><div><small>INFEASIBLE / 相互冲突的约束</small><h2>这张表没有任何可行整数解。</h2></div><span className="diagnostic-label sparse">{conflicts.length} 项冲突</span></header>
  <ol>{conflicts.map((c,i)=><li key={c.code+i}><strong>{c.title}</strong><p>{c.detail}</p>{c.code==='capacity_cut'&&<p className="fine">合计相等只是必要条件；逐格上下限还会通过行集合与列集合的联合容量产生额外冲突。</p>}</li>)}</ol>
 </section>;
}
