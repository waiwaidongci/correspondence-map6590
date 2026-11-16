import {useEffect,useState} from 'react';
import type {User,IntervalStudy,IntervalCategory,IntervalBound,IntervalRun,IntervalStudyDetail} from '../types/domain';
import {intervalApi} from '../api/intervals';
import {PageTitle} from '../components/common/PageTitle';
import {Notice} from '../components/common/Notice';
import {Empty} from '../components/common/Empty';
import {Badge} from '../components/common/Badge';
import {Table} from '../components/common/Table';
import {useAsync} from '../hooks/useAsync';
import {IntervalLadder} from '../components/IntervalLadder';
import {IntervalTable} from '../components/IntervalTable';
import {IntervalConflicts} from '../components/IntervalConflicts';
import {dec} from '../utils/format';

type IntervalPageProps={
 studies:IntervalStudy[];categories:IntervalCategory[];cells:IntervalBound[];runs:IntervalRun[];user:User;reload:()=>Promise<any>
};

const initialForm={
 name:'核定区间列联试例',
 rows:'家庭同行,学习小组,独立参访',
 columns:'故事导览,材料触摸,开放讨论',
 lower:'[[10,5,2],[4,10,3],[3,4,11]]',
 upper:'[[18,11,7],[10,17,9],[9,11,18]]',
 rowTotals:'28,26,26',
 colTotals:'25,28,27'
};

export function IntervalPage({studies,categories,cells,runs,user,reload}:IntervalPageProps){
 const [studyId,setStudyId]=useState(0);
 const [detail,setDetail]=useState<IntervalStudyDetail|null>(null);
 const [runId,setRunId]=useState(0);
 const [edit,setEdit]=useState<{row_id:number;column_id:number;lower:number;upper:number;cellId:number}|null>(null);
 const [total,setTotal]=useState<{id:number;value:number}|null>(null);
 const [name,setName]=useState('区间计数惯量上下界');
 const [timeLimit,setTimeLimit]=useState(20);
 const [show,setShow]=useState(false);
 const [form,setForm]=useState(initialForm);
 const {busy,error,message,act}=useAsync();
 const active=studyId||studies[0]?.id;
 const run=runs.find(r=>r.id===runId)||runs.find(r=>r.id&&r.study_id===active)||runs[0];
 useEffect(()=>{
  if(!active){setDetail(null);return}
  let alive=true;
  intervalApi.study(active).then(d=>{if(alive)setDetail(d)}).catch(()=>{if(alive)setDetail(null)});
  return()=>{alive=false}
 },[active,cells.length]);
 const rows=detail?.row_categories||[];
 const cols=detail?.column_categories||[];
 const lookup=new Map((detail?.cells||[]).map(c=>[c.row_id+':'+c.column_id,c]));
 function download(){if(run)act(()=>intervalApi.export(run.id),'区间结果已导出')}
 function importStudy(e:React.FormEvent){
  e.preventDefault();
  act(async()=>{
   const rowLabels=form.rows.split(/[,，]/).map((x,i)=>({code:'R'+(i+1),label:x.trim()}));
   const colLabels=form.columns.split(/[,，]/).map((x,i)=>({code:'C'+(i+1),label:x.trim()}));
   const rowTotals=form.rowTotals.split(/[,，]/).map(Number);
   const colTotals=form.colTotals.split(/[,，]/).map(Number);
   await intervalApi.create({
    name:form.name,filename:form.name+'.json',description:'研究员导入的区间计数；行列合计为已核实值',
    rows:rowLabels.map((r,i)=>({...r,verified_total:rowTotals[i]})),
    columns:colLabels.map((c,i)=>({...c,verified_total:colTotals[i]})),
    lower:JSON.parse(form.lower),upper:JSON.parse(form.upper)
   });
   await reload();setShow(false);setStudyId(0);
  },'区间研究已导入');
 }
 return <>
  <PageTitle index="07 / INTERVAL BOUNDS" title="没核清的格子，先给区间。" description="按类别填写每格整数上下限与已核实行列合计。原精确计数研究保持不变；这里求所有可行整数表的总惯量上下界，超时只报未证实与可行例子。"/>
  <Notice error={error||runs.find(r=>r.id===run?.id)?.error} message={message}/>
  <div className="study-selector">
   <label>当前区间研究
    <select value={active||''} onChange={e=>{setStudyId(+e.target.value);setRunId(0);setEdit(null)}}>
     {studies.map(s=><option key={s.id} value={s.id}>{s.name} / {s.rows}×{s.columns} / N={s.row_verified_total}</option>)}
    </select>
   </label>
   <p>{detail?.description||'尚无区间研究；可先导入一张上下限矩阵。'}<br/>{detail?.filename}</p>
  </div>
  {!studies.length&&<Empty title="还没有区间研究" help="导入行/列上下限矩阵与已核实合计，或运行seed演示数据。"/>}
  {detail&&<>
   <div className="interval-actions">
    <button onClick={()=>setShow(!show)}>{show?'收起导入表单':'导入区间矩阵 ↗'}</button>
    <button disabled={busy||!detail.totals_consistent} onClick={()=>act(async()=>{const r=await intervalApi.queue({study_id:detail.id,name,time_limit:timeLimit});await reload();setRunId(r.id)},'区间求解已排队')}>提交惯量上下界求解 →</button>
   </div>
   {show&&<form className="editor" onSubmit={importStudy}>
    <h2>上下限矩阵与已核实行列合计</h2>
    <label>研究名称<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} maxLength={100} required/></label>
    <div className="form-grid">
     <label>行类别 / 逗号分隔<input value={form.rows} onChange={e=>setForm({...form,rows:e.target.value})} required/></label>
     <label>列类别 / 逗号分隔<input value={form.columns} onChange={e=>setForm({...form,columns:e.target.value})} required/></label>
     <label>核实行合计 / 逗号分隔<input value={form.rowTotals} onChange={e=>setForm({...form,rowTotals:e.target.value})} required/></label>
     <label>核实列合计 / 逗号分隔<input value={form.colTotals} onChange={e=>setForm({...form,colTotals:e.target.value})} required/></label>
    </div>
    <div className="form-grid">
     <label>逐格整数下限 JSON<textarea rows={2} value={form.lower} onChange={e=>setForm({...form,lower:e.target.value})} required/></label>
     <label>逐格整数上限 JSON<textarea rows={2} value={form.upper} onChange={e=>setForm({...form,upper:e.target.value})} required/></label>
    </div>
    <button className="primary" disabled={busy}>校验并导入区间研究</button>
   </form>}
   <div className="interval-input-grid">
    <div>
     <div className="section-title"><h2>类别与已核实合计</h2><small>行列合计必须已核实且各自相等</small></div>
     <Table headers={['类别','轴','核实合计','校订']}>
      {[...rows,...cols].map(c=><tr key={c.id}>
       <td><small>{c.code}</small><strong>{c.label}</strong></td>
       <td>{c.axis==='row'?'行':'列'}</td>
       <td className="verified-total">{c.verified_total}</td>
       <td>{user.role!=='viewer'&&<button className="text-button" onClick={()=>setTotal({id:c.id,value:c.verified_total})}>改合计</button>}</td>
      </tr>)}
     </Table>
     {total&&<form className="editor cell-editor" onSubmit={e=>{e.preventDefault();act(async()=>{await intervalApi.total(total.id,total.value);await reload()},'已核实合计已校订')}}>
      <div><small>VERIFIED TOTAL</small><h3>校订该类别已核实的行列合计</h3></div>
      <label>核实合计<input type="number" min="0" max="144000000" step="1" value={total.value} onChange={e=>setTotal({...total,value:+e.target.value})} required/></label>
      <button className="primary" disabled={busy}>保存合计</button>
     </form>}
    </div>
    <div>
     <div className="section-title"><h2>逐格区间</h2><small>点击格子校订下限与上限</small></div>
     <Table headers={['行 × 列',...cols.map(c=>c.code)]}>
      {rows.map(r=><tr key={r.id}>
       <td><small>{r.code}</small><strong>{r.label}</strong></td>
       {cols.map(c=>{
        const cell=lookup.get(r.id+':'+c.id);
        const bound=cells.find(x=>x.row_id===r.id&&x.column_id===c.id);
        return <td key={c.id} className="interval-cell">{cell
         ?<button disabled={user.role==='viewer'} onClick={()=>setEdit({row_id:r.id,column_id:c.id,lower:cell.lower,upper:cell.upper,cellId:bound?.id||0})}>{cell.lower}–{cell.upper}</button>
         :'—'}</td>;
       })}
      </tr>)}
     </Table>
     {edit&&<form className="editor cell-editor" onSubmit={e=>{e.preventDefault();act(async()=>{await intervalApi.bound(edit.cellId,edit.lower,edit.upper);await reload();setEdit(null)},'区间已校订，审计保留')}}>
      <div><small>INTERVAL REVISION</small><h3>{rows.find(r=>r.id===edit.row_id)?.label} × {cols.find(c=>c.id===edit.column_id)?.label}</h3></div>
      <label>下限<input type="number" min="0" max="1000000" step="1" value={edit.lower} onChange={e=>setEdit({...edit,lower:+e.target.value})} required/></label>
      <label>上限<input type="number" min="0" max="1000000" step="1" value={edit.upper} onChange={e=>setEdit({...edit,upper:+e.target.value})} required/></label>
      <button className="primary" disabled={busy}>保存区间</button>
     </form>}
    </div>
   </div>
   {!!detail.input_conflicts.length&&<section className="interval-conflicts">
    <header><div><small>INPUT CHECK / 输入层面的冲突</small><h2>仅合计相等不足以保证可行。</h2></div><span className="diagnostic-label sparse">{detail.input_conflicts.length} 项</span></header>
    <ol>{detail.input_conflicts.map((c,i)=><li key={c.code+i}><strong>{c.title}</strong></li>)}</ol>
    <p className="fine">提交求解时会进一步用整数规划检查行集合与列集合的联合容量，给出最小割冲突明细。</p>
   </section>}
   <div className="config-grid interval-config">
    <div>
     <div className="section-title"><h2>求解配置</h2><small>超时只降级，不冒充精确极值</small></div>
     <div className="editor">
      <div className="form-grid">
       <label>求解名称<input value={name} onChange={e=>setName(e.target.value)} maxLength={100}/></label>
       <label>时间上限 / 秒<select value={timeLimit} onChange={e=>setTimeLimit(+e.target.value)}>{[5,10,20,30,45,60].map(v=><option key={v} value={v}>{v} 秒</option>)}</select></label>
      </div>
      <div className="protocol-check"><b>求解口径</b><p>先校验行/列合计与逐格上下限的整数可行性；再用整数规划求总惯量上下界。若时间上限内未收敛，页面显示已证范围与可行例子，并明确标注“未证实”。</p></div>
      <p className="fine">I(X)=Σ X_ij²/(R_i C_j) − 1，与精确计数分析的对应分析总惯量一致；零边际行/列贡献为0。</p>
     </div>
     <div className="section-title"><h2>求解队列</h2><small>worker 实际计算</small></div>
     <Table headers={['求解','研究','时限','状态','范围','']}>
      {runs.map(r=><tr key={r.id} className={run?.id===r.id?'selected':''}>
       <td><small>{r.name}</small><strong>#{r.id}</strong></td>
       <td>{studies.find(s=>s.id===r.study_id)?.name||'—'}</td>
       <td>{r.time_limit}s</td>
       <td><Badge status={r.status}/></td>
       <td>{r.status==='succeeded'&&r.result.feasible
        ?<>{dec(r.result.min?.value,4)} – {dec(r.result.max?.value,4)}<small>{r.result.exact?'已证实':'未证实'}</small></>
        :r.status==='failed'?'—':'等待'}</td>
       <td><button className="text-button" onClick={()=>setRunId(r.id)}>查看</button></td>
      </tr>)}
     </Table>
    </div>
    <aside className="method-notes">
     <small>BOUNDS / 三种读数</small>
     <h2>已证下界，<br/>可行例子，<br/>未证区间。</h2>
     <ol>
      <li><b>已证范围</b><p>来自整数规划对偶界，任何可行整数表都不能越过；若上下界与可行值重合，才称为精确极值。</p></li>
      <li><b>可行例子</b><p>每个界值都附一张满足全部上下限与行列合计的整数计数表，可下载复核。</p></li>
      <li><b>无解诊断</b><p>合计相等只是必要条件；逐格上下限会让部分行/列集合容量不足，页面给出行列集合与缺口。</p></li>
     </ol>
     <p className="fine">区间结果不改写既有精确计数研究，也不影响其运行与导出。</p>
    </aside>
   </div>
  </>}
  {run&&run.result?.feasible===false&&<IntervalConflicts conflicts={run.result.conflicts}/>}
  {run?.result?.feasible&&<>
   <IntervalLadder run={run}/>
   <IntervalTable run={run} which="min" onDownload={download}/>
   <IntervalTable run={run} which="max"/>
   {run.result.notes&&<p className="fine interval-notes">{run.result.notes.join(' ')}</p>}
  </>}
 </>;
}
