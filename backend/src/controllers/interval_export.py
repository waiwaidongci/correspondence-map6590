from fastapi import HTTPException
from src.models import IntervalRun
from src.utils.csv_export import csv_response

def export_interval_run(db,id):
 run=db.get(IntervalRun,id)
 if not run:raise HTTPException(404,'区间求解不存在')
 result=run.result or {}
 if run.status!='succeeded' or not result:raise HTTPException(409,'尚未完成，无法导出')
 rows=[]
 for side in ('min','max'):
  block=result.get(side) or {}
  table=block.get('table')
  if not table:continue
  for i,row in enumerate(table,1):
   rows.append([side,'boundary-count-table',f'R{i}',' '.join(str(v) for v in row)])
  rows.append([side,'value',block.get('value'),block.get('lower_bound') if side=='min' else block.get('upper_bound')])
 for conflict in result.get('conflicts',[]):
  rows.append(['conflict',conflict.get('code'),conflict.get('title'),conflict.get('detail')])
 rows.append(['summary','status',result.get('status'),'exact' if result.get('exact') else 'unproven'])
 rows.append(['summary','min_range',result.get('proven_range',{}).get('min_lower_bound'),result.get('proven_range',{}).get('min_feasible_value')])
 rows.append(['summary','max_range',result.get('proven_range',{}).get('max_feasible_value'),result.get('proven_range',{}).get('max_upper_bound')])
 return csv_response(f'interval-{id}.csv',rows,['side','field','value_a','value_b'])
