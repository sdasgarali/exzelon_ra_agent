
from sqlalchemy import create_engine, text

engine = create_engine(
    "mysql+pymysql://root:AdminRootDBAli@localhost:3306/cold_email_ai_agent?charset=utf8mb4"
)

migrations = [
    {"table": "client_info", "column": "status",
     "new_enum": "('active','inactive')",
     "mapping": {"ACTIVE": "active", "INACTIVE": "inactive"},
     "nullable": False, "default": None},
]

print("test")
