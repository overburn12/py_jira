from JiraClient import JiraClient
import os
from dotenv import load_dotenv

load_dotenv()
client = JiraClient()

test_data = client.get_order_summary("RT-17080")
print(test_data)