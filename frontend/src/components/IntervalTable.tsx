import type {IntervalBounds,IntervalRun} from '../types/domain';
import {Table} from './common/Table';
export function IntervalTable({run,which,onDownload}:{run:IntervalRun;which:'min'|'max';onDownload?:()=>void}){
 const r=run.result||{},block=(which==='min'?r.min:r.max) as IntervalBounds|undefined;
 if(!r.feasible||!block?.table)return null;
 const rows=r.row_categories||[],cols=r.column_categories||[];
 return <div className="interval-table-block">
  <div className="section-title"><h2>{which==='min'?'达到下界的计数表':'达到上界的计数表'}</h2>
   <small>{block.proved?'已由整数规划证实':'可行例子，不冒充极值'} · 总惯量 {block.value.toFixed(6)}</small></div>
  <Table headers={['行 × 列',...cols.map(c=>c.code+' / '+c.label),'核实行合计']}>
   {rows.map((row,i)=><tr key={row.id}><td><small>{row.code}</small><strong>{row.label}</strong></td>
    {cols.map((c,j)=><td key={c.id} className="interval-cell">{block.table![i][j]}</td>)}
    <td className="verified-total">{r.row_totals?.[i]}</td></tr>)}
   <tr className="total-row"><td><strong>核实列合计</strong></td>{cols.map((c,j)=><td key={c.id}>{r.column_totals?.[j]}</td>)}<td>{r.n}</td></tr>
  </Table>
  {onDownload&&<button className="text-button" onClick={onDownload}>下载区间结果 CSV ↗</button>}
 </div>;
}
