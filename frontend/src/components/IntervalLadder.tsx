import type {IntervalRun} from '../types/domain';
import {dec} from '../utils/format';

export function IntervalLadder({run}:{run:IntervalRun}){
 const r=run.result||{};
 const proven=r.proven_range,min=r.min,max=r.max;
 if(!r.feasible)return null;
 const lo=proven?.min_lower_bound??0,hi=proven?.max_upper_bound,feasibleMin=proven?.min_feasible_value??0,feasibleMax=proven?.max_feasible_value??0;
 const top=hi==null||!isFinite(hi)?Math.max(feasibleMax*1.35,feasibleMin+.5):Math.max(hi,1e-9);
 const scale=(v:number)=>Math.max(0,Math.min(100,v/top*100));
 const span=(a:number,b:number)=>Math.max(.6,scale(b)-scale(a));
 const pctOf=(v:number)=>v.toFixed(2)+'%';
 return <div className="interval-ladder">
  <div className="ladder-head"><small>PROVEN RANGE / 已证范围</small><span className={'diagnostic-label '+(r.exact?'usable':'sparse')}>{r.exact?'整数极值已证实':'超时降级 · 未证实'}</span></div>
  <div className="ladder-track" role="img" aria-label="总惯量的已证上下界与可行例子">
   <i className="ladder-band known" style={{left:pctOf(scale(lo)),width:pctOf(span(lo,feasibleMin))}} title="可证下界到最小可行值"/>
   <i className="ladder-band feasible" style={{left:pctOf(scale(feasibleMin)),width:pctOf(span(feasibleMin,feasibleMax))}} title="已找到的可行表覆盖的总惯量"/>
   <i className="ladder-band open" style={{left:pctOf(scale(feasibleMax)),width:pctOf(span(feasibleMax,top))}} title="可能仍有未证实区间"/>
  </div>
  <div className="ladder-legend">
   <span><i className="swatch known"/>0 → 已证下界 {dec(lo,6)}</span>
   <span><i className="swatch feasible"/>可行例子 {dec(feasibleMin,6)} – {dec(feasibleMax,6)}</span>
   <span><i className="swatch open"/>至 {hi==null||!isFinite(hi)?'未给出上界':dec(hi,6)}</span>
  </div>
  <div className="ladder-numbers">
   <div><small>最小总惯量</small><b>{dec(min?.value,6)}</b><span>{min?.proved?'已证实为最小值':'仅有可行值，下界 '+dec(min?.lower_bound,6)}</span></div>
   <div><small>最大总惯量</small><b>{dec(max?.value,6)}</b><span>{max?.proved?'已证实为最大值':'仅有可行值，上界 '+(max?.upper_bound==null?'未给出':dec(max.upper_bound,6))}</span></div>
  </div>
 </div>;
}
