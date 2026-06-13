import requests
import os
from dotenv import load_dotenv
from api.api_setup import *

########### Load Environment Variables ###########
load_dotenv()
api_base_url = os.getenv("API_BASE_URL")
api_port = os.getenv("API_PORT")
api_name = os.getenv("API_PATH")
full_api_url = f"{str(api_base_url)}:{str(api_port)}/{str(api_name)}"
print(f"Hitting this URL: {full_api_url}")

interest_rate = input("What is your current mortgage interest rate? Enter: ")
current_payment = input("What is your current mortgage payment (principal and interest only) Enter: ")
mortgage_balance = input("What is the current remaining balance on your mortgage? Enter: ")

########### Setup Test Framework ###########
def get_recommendation(interest_rate,
                       current_payment,
                       mortgage_balance) -> RefiAdviceResponse:

    print(f"Submitting an interest rate of: {interest_rate}\n")
    print(f"Submitting a current payment of: {current_payment}\n")
    print(f"Submitting a mortgage_balance of: {mortgage_balance}\n")

    data_output_dict = {
        "recommendation": "The agentic refinance tool recommendation is:",
        "num_tool_calls": "The total number of tools called was:",
        "path": "The path the agentic workflow took was:",
        "new_payment": "The estimated new monthly payment is:",
        "monthly_savings": "The estimated monthly savings is:",
        "break_even": "The estimated break even period (months) on the closing costs is:",
    }
    
    data_payload = RefiAdviceRequest(interest_rate=interest_rate,
                                     current_payment=current_payment,
                                     mortgage_balance=mortgage_balance).model_dump()

    result = requests.post(
        url=full_api_url,
        json=data_payload
    ).json()

    for key, text in data_output_dict.items():
        print(f"{text} {result.get(key)}\n")

    print("###########################")
    return result

# Run
get_recommendation(interest_rate, current_payment, mortgage_balance)

# poetry run python test_api_server.py