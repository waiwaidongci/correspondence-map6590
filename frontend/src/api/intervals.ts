import {request,post,download} from './client';
import type {IntervalStudy,IntervalStudyDetail,IntervalCategory,IntervalBound,IntervalRun} from '../types/domain';
export const intervalApi={
 studies:()=>request<IntervalStudy[]>('/interval/studies'),
 study:(id:number)=>request<IntervalStudyDetail>('/interval/studies/'+id),
 categories:()=>request<IntervalCategory[]>('/interval/categories'),
 cells:()=>request<IntervalBound[]>('/interval/cells'),
 create:(data:any)=>post('/interval/studies',data),
 bound:(id:number,lower:number,upper:number)=>request('/interval/cells/'+id,{method:'PATCH',body:JSON.stringify({lower,upper})}),
 total:(id:number,verified_total:number)=>request('/interval/categories/'+id,{method:'PATCH',body:JSON.stringify({verified_total})}),
 runs:()=>request<IntervalRun[]>('/interval/runs'),
 queue:(data:any)=>post('/interval/runs',data),
 export:(id:number)=>download('/interval/runs/'+id+'/export','interval-'+id+'.csv'),
};
