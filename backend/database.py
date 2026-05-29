from sqlmodel import Field, SQLModel, Session, create_engine, select
from typing import Optional
import bcrypt
from datetime import datetime, timezone


# tenant table
class Tenant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.now)


# user table
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    role: str = Field(default="staff")
    tenant_id: int = Field(foreign_key="tenant.id")


class AgentTrace(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    user_input: str
    final_response: str

    # observe
    latency_ms: float
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    estimated_cost: float = Field(default=0.0)

    # evaluate
    faithfulness: float = Field(default=1.0)
    hallucination_rate: float = Field(default=0.0)
    retrieval_quality: float = Field(default=1.0)

    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    created_at: datetime = Field(default_factory=datetime.now)


# Connect
sqlite_url = "sqlite:///./assistant.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def create_db_and_table():
    SQLModel.metadata.create_all(engine)


def seed_initial_data():
    with Session(engine) as session:
        existing_tenant = session.exec(select(Tenant)).first()
        if not existing_tenant:
            default_tenant = Tenant(name="Acme Corp")
            session.add(default_tenant)
            session.commit()
            session.refresh(default_tenant)

            hashed_pw = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            admin_user = User(
                username="admin",
                password_hash=hashed_pw,
                role="admin",
                tenant_id=default_tenant.id,
            )
            session.add(admin_user)
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
