from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.controllers.dependencies import current_user,writers
from src.controllers.interval_export import export_interval_run
from src.schemas.interval import IntervalStudyInput,IntervalCellPatch,IntervalTotalPatch,IntervalRunInput
from src.services import intervals
router=APIRouter(prefix='/interval')
@router.get('/studies')
def studies(db:Session=Depends(get_db),user=Depends(current_user)):return intervals.list_studies(db)
@router.get('/studies/{id}')
def study(id:int,db:Session=Depends(get_db),user=Depends(current_user)):return intervals.study_detail(db,id)
@router.post('/studies',status_code=201)
def create(data:IntervalStudyInput,db:Session=Depends(get_db),user=Depends(writers)):return intervals.create_study(db,data,user)
@router.get('/categories')
def categories(db:Session=Depends(get_db),user=Depends(current_user)):return intervals.list_categories(db)
@router.patch('/categories/{id}')
def category(id:int,data:IntervalTotalPatch,db:Session=Depends(get_db),user=Depends(writers)):return intervals.patch_total(db,id,data,user)
@router.get('/cells')
def cells(db:Session=Depends(get_db),user=Depends(current_user)):return intervals.list_bounds(db)
@router.patch('/cells/{id}')
def cell(id:int,data:IntervalCellPatch,db:Session=Depends(get_db),user=Depends(writers)):return intervals.patch_bound(db,id,data,user)
@router.get('/runs')
def runs(db:Session=Depends(get_db),user=Depends(current_user)):return intervals.list_runs(db)
@router.get('/runs/{id}')
def run(id:int,db:Session=Depends(get_db),user=Depends(current_user)):return intervals.get_run(db,id)
@router.post('/runs',status_code=201)
def queue(data:IntervalRunInput,db:Session=Depends(get_db),user=Depends(writers)):return intervals.create_run(db,data,user)
@router.get('/runs/{id}/export')
def export(id:int,db:Session=Depends(get_db),user=Depends(current_user)):return export_interval_run(db,id)
