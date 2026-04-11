# Major Features
## Features
- add stock splits and divedends to font
- Adding other yfinance ONLY ADD IF IT DOESNT BOG DOWN SYSTEM AND EASY TO GET. NOT OVER THE TOP API GRABS
    * major_holders
    * earnings_history
    * dividends
    * splits
    * institutional_holders
- Potentially add a noteworthy tab that displays stock-splits and their dates. also potentially add nearest earnings reports?


## QoL Features
### This is huge but everything states I must be careful not to have the same processer do the same command. This will cause issues 
- Increase the Gunicorn threads from 1 -4 to help backend
    * Right now your entire backend can only handle one request at a time  if two users click "run backtest" simultaneously, the second user waits in line until the first finishes, which can mean 5–10+ second delays for no good reason.
    * Most of your endpoints spend their time waiting on yfinance API calls and EFS reads, not actually using the CPU, so adding threads lets the server handle other users during that idle waiting time instead of sitting blocked.
    * The change costs $0/month and takes one line in Backend/Dockerfile:14, but effectively triples to quadruples the number of users the site can serve concurrently — turning a 3-user ceiling into a 10-user ceiling on the exact same Fargate task.



# Minor Improvments
- Add emails from users
    * potentially notify users of certain things
- Need to review strategies to usefulness. Maybe delete or add new ones
- Verify that Key Metrics and Fundimental data are accurate. % might not be calulated correctly
- Potentially Add Texas Stock Exchange if not already included
    * Not currently included — all market data comes from Yahoo Finance via yfinance (Backend/data_fetcher.py)
    * TXSE is pre-launch (targeting 2026); no public feed exists yet
    * Revisit once TXSE lists securities — if Yahoo ingests the TXSE feed, tickers may work through the existing pipeline (possibly with an exchange suffix like `.TX`); otherwise a separate provider integration would be needed
