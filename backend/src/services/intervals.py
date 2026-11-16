from sqlalchemy import select
from fastapi import HTTPException
from src.models import IntervalStudy,IntervalCategory,IntervalCellBound,IntervalRun
from src.constants.enums import RunStatus
from src.utils.serialize import row
from .audit import record

def list_studies(db):
 out=[]
 for study in db.scalars(select(IntervalStudy).order_by(IntervalStudy.id)):
  categories=list(db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==study.id)))
  bounds=list(db.scalars(select(IntervalCellBound).where(IntervalCellBound.study_id==study.id)))
  rows=[c for c in categories if c.axis=='row'];cols=[c for c in categories if c.axis=='column']
  out.append(dict(row(study),rows=len(rows),columns=len(cols),
   row_verified_total=sum(c.verified_total for c in rows),column_verified_total=sum(c.verified_total for c in cols),
   lower_total=sum(b.lower for b in bounds),upper_total=sum(b.upper for b in bounds)))
 return out

def list_categories(db):
 return [row(x) for x in db.scalars(select(IntervalCategory).order_by(IntervalCategory.study_id,IntervalCategory.axis,IntervalCategory.position))]

def list_bounds(db):
 return [row(x) for x in db.scalars(select(IntervalCellBound).order_by(IntervalCellBound.id))]

def _input_conflicts(db,study_id):
 """Totals-level conflicts visible without solving; purely advisory."""
 rows=[row(x) for x in db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==study_id,IntervalCategory.axis=='row').order_by(IntervalCategory.code))]
 cols=[row(x) for x in db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==study_id,IntervalCategory.axis=='column').order_by(IntervalCategory.code))]
 bounds={(b.row_id,b.column_id):b for b in db.scalars(select(IntervalCellBound).where(IntervalCellBound.study_id==study_id))}
 issues=[]
 if sum(r['verified_total'] for r in rows)!=sum(c['verified_total'] for c in cols):
  issues.append({'code':'totals_mismatch','title':'核实行合计之和与核实列合计之和不相等'})
 for r in rows:
  lower_total=sum(bounds[(r['id'],c['id'])].lower for c in cols if (r['id'],c['id']) in bounds)
  upper_total=sum(bounds[(r['id'],c['id'])].upper for c in cols if (r['id'],c['id']) in bounds)
  if lower_total>r['verified_total']:issues.append({'code':'row_lower_over_total','title':f"行 {r['code']} 下限合计超过核实行合计"})
  if upper_total<r['verified_total']:issues.append({'code':'row_upper_under_total','title':f"行 {r['code']} 上限合计小于核实行合计"})
 for c in cols:
  lower_total=sum(bounds[(r['id'],c['id'])].lower for r in rows if (r['id'],c['id']) in bounds)
  upper_total=sum(bounds[(r['id'],c['id'])].upper for r in rows if (r['id'],c['id']) in bounds)
  if lower_total>c['verified_total']:issues.append({'code':'col_lower_over_total','title':f"列 {c['code']} 下限合计超过核实列合计"})
  if upper_total<c['verified_total']:issues.append({'code':'col_upper_under_total','title':f"列 {c['code']} 上限合计小于核实列合计"})
 return issues

def study_detail(db,id):
 study=db.get(IntervalStudy,id)
 if not study:raise HTTPException(404,'区间研究不存在')
 rows=[row(x) for x in db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==id,IntervalCategory.axis=='row').order_by(IntervalCategory.code))]
 cols=[row(x) for x in db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==id,IntervalCategory.axis=='column').order_by(IntervalCategory.code))]
 bounds=[row(x) for x in db.scalars(select(IntervalCellBound).where(IntervalCellBound.study_id==id))]
 lookup={(b['row_id'],b['column_id']):b for b in bounds}
 return dict(row(study),row_categories=rows,column_categories=cols,cells=[
  {'row_id':r['id'],'column_id':c['id'],'lower':lookup[(r['id'],c['id'])]['lower'],'upper':lookup[(r['id'],c['id'])]['upper']}
  for r in rows for c in cols if (r['id'],c['id']) in lookup
 ],totals_consistent=sum(r['verified_total'] for r in rows)==sum(c['verified_total'] for c in cols),
  input_conflicts=_input_conflicts(db,id))

def bound_data(db,id):
 """Matrices for the solver, including category labels for conflict messages."""
 study=db.get(IntervalStudy,id)
 if not study:raise HTTPException(404,'区间研究不存在')
 rows=[row(x) for x in db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==id,IntervalCategory.axis=='row').order_by(IntervalCategory.code))]
 cols=[row(x) for x in db.scalars(select(IntervalCategory).where(IntervalCategory.study_id==id,IntervalCategory.axis=='column').order_by(IntervalCategory.code))]
 bounds=[row(x) for x in db.scalars(select(IntervalCellBound).where(IntervalCellBound.study_id==id))]
 lookup={(b['row_id'],b['column_id']):b for b in bounds}
 lower=[[lookup.get((r['id'],c['id']),{'lower':0})['lower'] for c in cols] for r in rows]
 upper=[[lookup.get((r['id'],c['id']),{'upper':0})['upper'] for c in cols] for r in rows]
 return row(study),rows,cols,bounds,lower,upper,[r['verified_total'] for r in rows],[c['verified_total'] for c in cols]

def create_study(db,data,user):
 if db.scalar(select(IntervalStudy).where(IntervalStudy.name==data.name)):raise HTTPException(409,'区间研究名称已存在')
 study=IntervalStudy(**data.model_dump(exclude={'rows','columns','lower','upper'}))
 db.add(study);db.flush()
 groups={}
 for axis,items in (('row',data.rows),('column',data.columns)):
  group=[]
  for i,item in enumerate(items):
   category=IntervalCategory(study_id=study.id,axis=axis,position=i,**item.model_dump());db.add(category);db.flush();group.append(category)
  groups[axis]=group
 for i,r in enumerate(groups['row']):
  for j,c in enumerate(groups['column']):
   db.add(IntervalCellBound(study_id=study.id,row_id=r.id,column_id=c.id,lower=data.lower[i][j],upper=data.upper[i][j]))
 db.commit();record(db,user.email,'interval.study.import',{'study_id':study.id});return study_detail(db,study.id)

def patch_bound(db,id,data,user):
 bound=db.get(IntervalCellBound,id)
 if not bound:raise HTTPException(404,'区间单元格不存在')
 bound.lower=data.lower;bound.upper=data.upper
 db.commit();record(db,user.email,'interval.bounds.updated',{'cell_id':id,'lower':bound.lower,'upper':bound.upper})
 return row(bound)

def patch_total(db,id,data,user):
 category=db.get(IntervalCategory,id)
 if not category:raise HTTPException(404,'区间类别不存在')
 category.verified_total=data.verified_total
 db.commit();record(db,user.email,'interval.total.updated',{'category_id':id,'verified_total':category.verified_total})
 return row(category)

def list_runs(db):
 return [row(x) for x in db.scalars(select(IntervalRun).order_by(IntervalRun.id.desc()))]

def get_run(db,id):
 run=db.get(IntervalRun,id)
 if not run:raise HTTPException(404,'区间求解不存在')
 return run

def create_run(db,data,user):
 if not db.get(IntervalStudy,data.study_id):raise HTTPException(404,'区间研究不存在')
 conflicts=_input_conflicts(db,data.study_id)
 if conflicts and any(x['code']=='totals_mismatch' for x in conflicts):
  raise HTTPException(422,'行合计之和与列合计之和必须先相等；请先校订已核实合计')
 run=IntervalRun(study_id=data.study_id,name=data.name,time_limit=data.time_limit,creator_id=user.id)
 db.add(run);db.commit()
 from src.worker import solve_interval_run
 try:
  solve_interval_run.delay(run.id)
 except Exception:
  run.status=RunStatus.FAILED;run.error='队列不可用';db.commit();raise HTTPException(503,run.error)
 record(db,user.email,'interval.queued',{'run_id':run.id,'time_limit':data.time_limit})
 return row(run)
