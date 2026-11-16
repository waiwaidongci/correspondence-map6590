from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,JSON,ForeignKey,DateTime,UniqueConstraint,CheckConstraint
from datetime import datetime,timezone
from src.config.database import Base
class IntervalStudy(Base):
 __tablename__='interval_studies'
 id:Mapped[int]=mapped_column(primary_key=True)
 name:Mapped[str]=mapped_column(String(100),unique=True)
 filename:Mapped[str]=mapped_column(String(160))
 description:Mapped[str]=mapped_column(String(500),default='')
class IntervalCategory(Base):
 __tablename__='interval_categories'
 __table_args__=(UniqueConstraint('study_id','axis','code'),CheckConstraint('verified_total>=0',name='interval_total_nonnegative'))
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('interval_studies.id'))
 axis:Mapped[str]=mapped_column(String(10))
 code:Mapped[str]=mapped_column(String(30))
 label:Mapped[str]=mapped_column(String(80))
 position:Mapped[int]=mapped_column()
 verified_total:Mapped[int]=mapped_column(default=0)
class IntervalCellBound(Base):
 __tablename__='interval_cell_bounds'
 __table_args__=(UniqueConstraint('row_id','column_id'),CheckConstraint('lower>=0 AND upper>=lower',name='interval_bounds_ordered'))
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('interval_studies.id'))
 row_id:Mapped[int]=mapped_column(ForeignKey('interval_categories.id'))
 column_id:Mapped[int]=mapped_column(ForeignKey('interval_categories.id'))
 lower:Mapped[int]=mapped_column(default=0)
 upper:Mapped[int]=mapped_column(default=0)
class IntervalRun(Base):
 __tablename__='interval_runs'
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('interval_studies.id'))
 name:Mapped[str]=mapped_column(String(100))
 time_limit:Mapped[int]=mapped_column(default=20)
 status:Mapped[str]=mapped_column(String(20),default='queued')
 result:Mapped[dict]=mapped_column(JSON,default=dict)
 error:Mapped[str|None]=mapped_column(String(1000),nullable=True)
 creator_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
