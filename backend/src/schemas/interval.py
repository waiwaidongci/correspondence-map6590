from pydantic import BaseModel,Field,StrictInt,model_validator
class IntervalCategoryInput(BaseModel):
 code:str=Field(min_length=1,max_length=30)
 label:str=Field(min_length=1,max_length=80)
 verified_total:StrictInt=Field(ge=0,le=144000000)
class IntervalStudyInput(BaseModel):
 name:str=Field(min_length=1,max_length=100)
 filename:str=Field(min_length=1,max_length=160)
 description:str=Field(default='',max_length=500)
 rows:list[IntervalCategoryInput]=Field(min_length=2,max_length=12)
 columns:list[IntervalCategoryInput]=Field(min_length=2,max_length=12)
 lower:list[list[StrictInt]]
 upper:list[list[StrictInt]]
 @model_validator(mode='after')
 def validate_table(self):
  if len({x.code for x in self.rows})!=len(self.rows) or len({x.code for x in self.columns})!=len(self.columns):raise ValueError('同一轴类别code不得重复')
  for name,matrix in (('下限',self.lower),('上限',self.upper)):
   if len(matrix)!=len(self.rows) or any(len(row)!=len(self.columns) for row in matrix):raise ValueError(f'{name}矩阵维度与类别不匹配')
   if any(type(c)!=int or not 0<=c<=1000000 for row in matrix for c in row):raise ValueError(f'{name}须0..1000000整数')
  for i,row in enumerate(self.lower):
   for j,low in enumerate(row):
    if low>self.upper[i][j]:raise ValueError('每个格子的下限不得大于上限')
  if sum(x.verified_total for x in self.rows)!=sum(x.verified_total for x in self.columns):raise ValueError('核实行合计之和须等于核实列合计之和')
  return self
class IntervalCellPatch(BaseModel):
 lower:StrictInt=Field(ge=0,le=1000000)
 upper:StrictInt=Field(ge=0,le=1000000)
 @model_validator(mode='after')
 def validate_bounds(self):
  if self.lower>self.upper:raise ValueError('下限不得大于上限')
  return self
class IntervalTotalPatch(BaseModel):
 verified_total:StrictInt=Field(ge=0,le=144000000)
class IntervalRunInput(BaseModel):
 study_id:int=Field(gt=0)
 name:str=Field(min_length=1,max_length=100)
 time_limit:int=Field(ge=5,le=60,strict=True)
