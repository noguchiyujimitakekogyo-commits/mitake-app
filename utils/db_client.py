File "/mount/src/mitake-app/app.py", line 16, in <module>
    from views.budget import render_budget
File "/mount/src/mitake-app/views/budget.py", line 8, in <module>
    from utils.db_client import db
File "/mount/src/mitake-app/utils/db_client.py", line 11, in <module>
    cred = credentials.Certificate("serviceAccountKey.json")
File "/home/adminuser/venv/lib/python3.14/site-packages/firebase_admin/credentials.py", line 97, in __init__
    with open(cert, encoding='utf-8') as json_file:
         ~~~~^^^^^^^^^^^^^^^^^^^^^^^^