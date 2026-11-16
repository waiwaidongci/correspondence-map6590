import json
from sqlalchemy import select,func
from src.config.database import Base,engine,SessionLocal
from src.models import *
from src.utils.security import hash_password
from src.services.catalog import table_data
from src.services.ca import correspondence
from src.services.fingerprint import fingerprint
from src.services.interval_solver import solve_interval

def seed():
 Base.metadata.create_all(engine)
 with SessionLocal() as db:
  for role,name in [('admin','许禾 · 展陈研究负责人'),('analyst','陈陌 · 偏好结构研究员'),('viewer','林叙 · 导览观察员')]:
   email=role+'@hemo.demo'
   if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,name=name,role=role,password_hash=hash_password('Hemo2026!')))
  db.commit()
  scenarios=[('秋季导览类别研究',['家庭同行','学习小组','独立参访','策展同业'],['故事导览','材料触摸','开放讨论','地图路径','静观笔记'],[[120,38,18,30,19],[27,112,36,27,23],[24,33,120,27,21],[45,42,27,75,36]]),('接近独立的对照折页',['A类参访','B类参访','C类参访','D类参访'],['文字','触摸','讨论','路径','笔记'],[[46,44,45,45,45],[45,46,44,45,45],[45,45,46,44,45],[44,45,45,46,45]]),('稀疏试采与零边际',['交流团','工坊团','研究团','零样本类','随访团'],['文字卡','互动台','声景线','零样本列'],[[2,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,0],[1,0,1,0]])]
  for index,(name,rowlabels,collabels,table) in enumerate(scenarios,1):
   if db.scalar(select(ContingencyStudy).where(ContingencyStudy.name==name)):continue
   study=ContingencyStudy(name=name,filename=f'hm-guide-contingency-{index}.csv',description='机构级匿名类别计数；合成展陈工作流，不作人群因果推断。');db.add(study);db.flush();groups=[]
   for axis,labels in [('row',rowlabels),('column',collabels)]:
    group=[]
    for i,label in enumerate(labels):
     category=Category(study_id=study.id,axis=axis,code=('R' if axis=='row' else 'C')+str(i+1),label=label,position=i);db.add(category);db.flush();group.append(category)
    groups.append(group)
   for i,r in enumerate(groups[0]):
    for j,c in enumerate(groups[1]):db.add(CellCount(study_id=study.id,row_id=r.id,column_id=c.id,count=table[i][j]))
   db.commit()
  if not db.scalar(select(CorrespondenceRun).where(CorrespondenceRun.name=='秋季导览结构初稿')):
   study=db.scalar(select(ContingencyStudy).where(ContingencyStudy.name==scenarios[0][0]));meta,rows,cols,cells,table=table_data(db,study.id);result=correspondence(table,rows,cols,2);result['fingerprint']=fingerprint(meta,rows,cols,cells,2);admin=db.scalar(select(User).where(User.role=='admin'));run=CorrespondenceRun(study_id=study.id,name='秋季导览结构初稿',axes=2,status='succeeded',result=result,creator_id=admin.id);db.add(run);db.flush();db.add(InterpretationNote(run_id=run.id,name='行轮廓结构与导览小样草案',category_ids=[p['id'] for p in result['row_points'][:2]],interpretation='先读取同行轮廓与显示质量，不把行列两点间接近当成直接偏好距离。',next_step='保留完整惯量和期望计数诊断，再做独立导览小样试验。',creator_id=admin.id));db.add(AuditLog(actor='seed',action='demo.created',detail={'total_counts':1806,'tables':3}));db.commit()
  seed_interval(db)
  counts={t.__tablename__:db.scalar(select(func.count()).select_from(t)) for t in [User,ContingencyStudy,Category,CellCount,CorrespondenceRun,InterpretationNote,IntervalStudy,IntervalCategory,IntervalCellBound,IntervalRun]};print(json.dumps(counts));return counts

def seed_interval(db):
 name='秋季导览内核定计数区间'
 if db.scalar(select(IntervalStudy).where(IntervalStudy.name==name)):return
 study=IntervalStudy(name=name,filename='hm-guide-interval-1.csv',description='尚未核清的格子只写上下限；行/列合计为已核实值。区间研究不改动原精确计数研究。')
 db.add(study);db.flush()
 row_labels=['家庭同行','学习小组','独立参访','策展同业'];col_labels=['故事导览','材料触摸','开放讨论','地图路径','静观笔记']
 row_totals=[225,225,225,225];col_totals=[216,225,201,159,99]
 lower=[[112,34,18,25,15],[22,106,32,23,18],[20,29,113,23,18],[39,37,23,67,36]]
 upper=[[128,42,18,35,23],[32,118,40,31,28],[28,37,127,31,24],[51,47,31,83,36]]
 groups={}
 for axis,labels,totals in (('row',row_labels,row_totals),('column',col_labels,col_totals)):
  group=[]
  for i,(label,total) in enumerate(zip(labels,totals)):
   category=IntervalCategory(study_id=study.id,axis=axis,code=('R' if axis=='row' else 'C')+str(i+1),label=label,position=i,verified_total=total)
   db.add(category);db.flush();group.append(category)
  groups[axis]=group
 for i,r in enumerate(groups['row']):
  for j,c in enumerate(groups['column']):
   db.add(IntervalCellBound(study_id=study.id,row_id=r.id,column_id=c.id,lower=lower[i][j],upper=upper[i][j]))
 db.commit()
 if not db.scalar(select(IntervalRun).where(IntervalRun.study_id==study.id)):
  result=solve_interval(lower,upper,row_totals,col_totals,time_limit=12,row_labels=[f'R{i+1} {x}' for i,x in enumerate(row_labels)],col_labels=[f'C{j+1} {x}' for j,x in enumerate(col_labels)])
  result['study']={'id':study.id,'name':name,'filename':study.filename,'description':study.description}
  result['row_categories']=[{'id':r.id,'code':r.code,'label':r.label,'verified_total':r.verified_total} for r in groups['row']]
  result['column_categories']=[{'id':c.id,'code':c.code,'label':c.label,'verified_total':c.verified_total} for c in groups['column']]
  admin=db.scalar(select(User).where(User.role=='admin'))
  db.add(IntervalRun(study_id=study.id,name='区间惯量上下界初稿',time_limit=12,status='succeeded',result=result,creator_id=admin.id))
  db.add(AuditLog(actor='seed',action='interval.demo.created',detail={'study_id':study.id,'status':result['status']}))
  db.commit()
if __name__=='__main__':seed()
