from datetime import timedelta
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.utils.dates import days_ago

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'controlSaldos',
    default_args=default_args,
    description='A simple DAG to run a Python script daily at 8am',
    schedule_interval='0 8 * * *',
    start_date=days_ago(1),
)

t1 = BashOperator(
    task_id='run_python_script',
    bash_command='python3 /home/control/control.py',
    dag=dag,
)

########################
from datetime import timedelta
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.utils.dates import days_ago

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'controlSaldosTest',
    default_args=default_args,
    description='A simple DAG to run a Python script daily',
    schedule_interval='53 21 * * *',
    start_date=days_ago(1),
)

t1 = BashOperator(
    task_id='run_python_script',
    bash_command='python3 /home/control/control.py',
    dag=dag,
)