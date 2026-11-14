from alembic import context
from sqlalchemy import create_engine
from mail_tools.app.store import metadata

configuration=context.config
connection=configuration.attributes.get("connection")
if connection is not None:
    context.configure(connection=connection,target_metadata=metadata)
    with context.begin_transaction():context.run_migrations()
else:
    from mail_tools.app.config import config
    directory=config().database_dir
    directory.mkdir(parents=True,exist_ok=True)
    engine=create_engine(f"sqlite:///{directory/'operations.sqlite'}")
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=metadata)
        with context.begin_transaction():context.run_migrations()
