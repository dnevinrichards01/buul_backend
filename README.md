
# Welcome to the backend of Buul
*Tutorial below; More details available upon request*

See other parts of Buul
- [AWS (Terraform) architecture](https://github.com/dnevinrichards01/buul_terraform) 
- [iOS (SwiftUI) front-end](https://github.com/dnevinrichards01/buul_app)
- [Custom robinhood integration](https://github.com/dnevinrichards01/buul_robinstocks/tree/main)
- [Original Buul website (React)](https://github.com/dnevinrichards01/accumate_frontend)
- [Original Buul website interactive graph (React)](https://buul-site-graph.vercel.app/), *[[github repo](https://github.com/dnevinrichards01/buul-site-graph)]*
- [Final Buul website (Framer)](https://bu-ul.com)

### About

#### Buul is a personal finance app that:
1. **automatically invests and maximizes your credit-card cashback**
2. converts **spending into compound interest**
3. is tackling the retirement crisis

#### Backend Tech Stack:
1. Django Rest Framework app servers
2. Celery background workers
3. PostgreSQL database 
4. Redis cache and AWS-SQS to coordinate background workers
5. AWS-KMS for envelope encryption, NGINX for HTTPS
6. Docker to containerize application
7. Supervisord to manage processes on the containers

#### Key Features:
1. Real-time portfolio graph
2. Plaid Integration to connect to your bank account and automatically detect cashback
3. [DIY Robinhood brokerage integration](https://github.com/dnevinrichards01/buul_robinstocks/tree/main) built with Postman and [`robinstocks` library](https://github.com/jmfernandes/robin_stocks)
4. Email-based OTP to verify identity before changing account information
5. Envelope encryption of sensitive fields including keys upon each database access

https://github.com/user-attachments/assets/cd1a3976-a301-4b2e-93d8-8b113fcaab45

*[(youtube link)](https://youtu.be/KxmgHJfnfms?si=C_SQuw_YTHzXiI8z)*

#### Some Files / Landmarks of Interest:
##### 0. Three basic sections
- Backend endpoints in `api/views.py` and `api/urls.py`
- Background worker tasks and helper methods in `api/tasks/*`
- Data models in `api/models.py`
##### 1. Identifying cashback from bank account, and depositing and investing cashback in Robinhood
- `api/tasks/identify`
- `api/tasks/deposit`
- `api/tasks/invest` 
- These files use our custom [`buul_robinstocks`](https://github.com/dnevinrichards01/buul_robinstocks/tree/main) integration with Robinhood 
##### 2. Refresh and update stock prices and users' investment graphs
- `api/tasks/graph/py`
- `class StockGraphData` in `api/views.py`
##### 3. Plaid integration
- classes `PlaidUserCreate`, `PlaidLinkTokenCreate`, `PlaidItemWebhook` in `api/views.py`
- functions starting with `plaid` in `api/tasks/user.py` 
##### 4. Encryption 
- `conf_files/nginx.conf`
- models with `BinaryField` in `api/models.py`
- `buul_backend/encryption`

### Tutorial: try it out yourself!

*This code is not currently being maintained*

*Use this and the code / comments in `tutorial/*` as a guide if debugging / if you encounter an Exception.*

#### Prereqs:
Clone the try_it_out_local branches for the [backend](https://github.com/dnevinrichards01/buul_backend/tree/try_it_out_local) and ios [frontend](https://github.com/dnevinrichards01/buul_app/tree/try_it_out_local). 
```
git clone --recursive https://github.com/dnevinrichards01/buul_backend.git

git clone https://github.com/dnevinrichards01/buul_app.git
```

Enter each repo and move to the `try_it_out_local` branch:
```
git checkout origin/try_it_out_local
```

To use the front-end code, you will need to use XCode and its iphone simulator – this may require a mac. You will also need to have installed docker and docker compose.

#### 1. Create backend containers
Enter the backend repo, then run:
```
docker compose -f build_files/docker-compose.yml --project-directory . build

docker compose -f build_files/docker-compose.yml --project-directory . up -d
```
After roughly 30 seconds, the containers should be done setting up. Running:
```
docker compose -f build_files/docker-compose.yml --project-directory . logs web | head -n 4

docker compose -f build_files/docker-compose.yml --project-directory . logs celery | head -n 4 
```
should return outputs similar to 
```
gunicorn entered RUNNING state, process has stayed up for > than 1 seconds 
```
#### 2. Run the front end with a simulation of an iPhone using XCode.

First, in the menu bar at the top of the screen, click `Product >> Destination >> iPhone 16` to allow simulating an iphone.

Next, click `cmd + r` or `Product >> Run` to run the simulation.

#### 3. Follow the sign up flow
This will be intuitive, but here are three things to keep in mind:
1. You will recieve an email from nevintesting00@gmail.com when recieving verification codes. 
2. When asked to select your brokerage:
    - selecting Robinhood will log into your Robinhood brokerage account account. 
    - The other brokerages cannot yet be connected to, so select them to avoid connecting to a brokerage 
3. When going through the Plaid connection, you will be asked to enter your phone number on the first and last page. Instead, select the 'continue as guest' option on the first page. And on the final page, click 'finish without saving'

#### 4. Once on the home page, populate the portfolio graph with one (or both) of two methods.

First, go back to where you are running the backend and log onto the web app's container.
```
docker compose -f build_files/docker-compose.yml --project-directory . exec web bash

python manage.py shell < tutorial/initialize_stock_data.py
```
#### Method 1: Deposit and Invest 1 dollar with Robinhood 

If you do this, I recommend you do it first so it is easily visible in the graph. We create a fake cashback record, which usually would have been automatically detected from Plaid's connection to a user's bank accounts.
```
python manage.py shell < tutorial/create_test_cashback.py
```
Optionally, confirm the cashback object's existence in the database.

```
python manage.py shell

from api.models import *; from api.tasks import *

cashback = PlaidCashbackTransaction.objects.filter(user=User.objects.first(), deposit=None, flag=False)

print(f"There are {cashback.count()} cashback objects")

print(f"Here are their dollar amount, name, and date: {cashback.values('amount', 'name', 'date')}")

exit()
```

Next, we will deposit the cashback into our Robinhood account. Note that you MUST have a checking or savings account linked to your Robinhood account rather than using direct deposit.
```
python manage.py shell < tutorial/deposit_test_cashback.py
```
Optionally, confirm that the deposit was recorded in the database.
```
python manage.py shell

from api.models import *; from api.tasks import *

deposit = Deposit.objects.filter(user=User.objects.first()).order_by('-created_at').first()

print(f"The deposit was made at {deposit.created_at} for {deposit.early_access_amount} USD")

exit()
```

Finally, we will invest the deposited 1 dollar into the ETF "VOO" through Robinhood.
```
python manage.py shell < tutorial/invest_test_cashback.py
```
Optionally, confirm that the investment was recorded in the database.
```
python manage.py shell

from api.models import *; from api.tasks import *

investment = Investment.objects.filter(user=User.objects.first()).order_by('-date').first()

print(f"The investment was made at {investment.date} for {investment.rh.requested_amount} USD")

exit()
```

You'll now be able to see the investment in your home page after 1-2 minutes! If you would like to forcefully refresh the page sooner, you may click on one of the settings page's options then go back to the home page. 

#### Method 2: Generate fake investments
```
python manage.py shell < tutorial/create_test_investments.py
```

#### 5. Graph automatically updates
You'll now be able to see the investment in your home page after 2-5 minutes (the free `yfinance` stocks API used for this tutorial causes delays).
The page refreshes every minute, but you may forcefully refresh by clicking on one of the settings page's options then going back to the home page.


