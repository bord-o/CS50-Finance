import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user_id = session["user_id"]
    user_cash = db.execute("SELECT cash FROM 'users' WHERE id = '{0}'".format(user_id))[0]["cash"]

    transactions = db.execute("select * from 'transactions' where id = '{0}'".format(user_id))

    total_assets = user_cash
    for entry in transactions:
        updated_price = lookup(entry["symbol"])["price"]
        entry["updated_price"] = updated_price

        total_assets += (entry["updated_price"] - entry["price"]) * entry["shares"]

    print(transactions)

    # return render_template("index.html",user_cash=user_cash, user_total=user_total, trading_at=trading_at, position_value=position_value, transactions=transactions)
    return render_template("index.html", user_cash=user_cash,  transactions=transactions, user_total=total_assets)
    # return apology("TODO")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        # get symbol and number of shares
        sym = request.form.get("symbol")
        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("enter valid number of shares", 400)

        if shares < 1:
            return apology("must enter number of shares", 400)
        # get api data
        lookup_results = lookup(sym)

        # validate api call
        if lookup_results == None:
            return apology("Stock symbol not found", 400)
        share_price = lookup_results["price"]

        # get user's cash total from db and make sure they can afford the transaction
        user_cash = db.execute("SELECT cash FROM 'users' WHERE id = '{0}'".format(session["user_id"]))[0]["cash"]
        trans_total = share_price * shares
        if user_cash < trans_total:
            return apology("not enough cash", 400)

        # execute transaction by updateing db
        # update users cash, and add an entry to the transactions table
        db.execute("insert into 'history' ('id', 'symbol', 'price', 'shares', 'operation') values ('{0}', '{1}', {2}, {3}, '{4}')".format(
            session["user_id"], lookup_results["symbol"], share_price, shares, 'buy'))
        db.execute("INSERT INTO 'transactions' ('id','symbol','price','shares') VALUES ('{0}','{1}','{2}','{3}')".format(
            session["user_id"], lookup_results["symbol"], share_price, shares))
        db.execute("update 'users' set cash=((select cash from 'users' where id='{0}') - {1}) where id='{0}'".format(
            session["user_id"], int(trans_total)))
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]
    transactions = db.execute("select * from 'history' where id = '{0}'".format(user_id))

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    else:
        sym = request.form.get("symbol")
        lookup_results = lookup(sym)
        if lookup_results == None:
            return apology("symbol not found", 400)

        lookup_time = datetime.date.today()
        return render_template("quoted.html", lookup_results=lookup_results, lookup_time=lookup_time)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password confirmation doesn't match", 400)

        # pull uname and pass from document
        uname = request.form.get("username")
        password = request.form.get("password")

        # check if user is unique by querying database
        try:
            not_uniq = db.execute("SELECT * FROM 'users' WHERE username='{0}'".format(uname))
            if not_uniq:
                return apology("username not unique", 400)
        except:
            pass

        # find the current highest id and increment for by one for next user
        highest_id = db.execute("SELECT id FROM 'users' WHERE id = (select max(id) from 'users')")[0]["id"]

        new_id = highest_id + 1
        new_hash = generate_password_hash(password)

        # add user info to database
        db.execute("INSERT INTO 'users' ('id','username','hash') VALUES ('{0}','{1}','{2}')".format(new_id, uname, new_hash))

        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = session["user_id"]
    transactions = db.execute("select * from 'transactions' where id = '{0}' order by symbol, shares desc".format(user_id))

    # loop to create unique dict of symbols and total shares
    owned_symbols = {}
    for entry in transactions:
        if entry["symbol"] in owned_symbols:
            owned_symbols[entry["symbol"]] = owned_symbols.get(entry["symbol"]) + entry["shares"]
        else:
            owned_symbols[entry["symbol"]] = entry["shares"]

    if request.method == "GET":

        print(owned_symbols)
        return render_template("sell.html", owned_symbols=owned_symbols)
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        try:
            shares = int(shares)
        except:
            return apology("enter valid number of shares", 400)
        if shares < 1:
            return apology("enter valid number of shares", 400)

        if shares > owned_symbols.get(symbol):
            return apology("you can only sell the shares you own", 400)

        db.execute("insert into 'history' ('id', 'symbol', 'price', 'shares', 'operation') values ('{0}', '{1}', {2}, {3}, '{4}')".format(
            user_id, symbol, lookup(symbol)["price"], shares, 'sell'))
        # need to algorithmically sell all of the stock requested by looping through positions and selling the required amount
        # since transactions are sorted above, I check to see if the biggest position is enough to satisfy the sell, otherwise,
        # we liquidate the entire position and move to the second largest.
        transactions_to_sell = db.execute(
            "select * from 'transactions' where id = '{0}' and symbol='{1}' order by symbol, shares desc".format(user_id, symbol))
        while shares > 0:
            for entry in transactions_to_sell:
                updated_price = lookup(entry["symbol"])["price"]

                if entry["shares"] > shares:
                    # sell only whats needed
                    sold_amount = updated_price * shares
                    db.execute(
                        "update 'transactions' set shares=shares-{2} WHERE time='{0}' and id='{1}'".format(entry["time"], user_id, shares))
                    db.execute("update 'users' set cash=cash+'{0}' where id='{1}'".format(sold_amount, user_id))
                    return redirect("/")
                else:
                    # sell entire postion and continue iteration
                    sold_amount = updated_price * entry["shares"]
                    shares -= entry["shares"]
                    db.execute(
                        "update 'transactions' set shares=shares-{2} WHERE time='{0}' and id='{1}'".format(entry["time"], user_id, entry["shares"]))
                    db.execute("update 'users' set cash=cash+'{0}' where id='{1}'".format(sold_amount, user_id))
        return redirect("/")


@app.route("/add", methods=["POST"])
@login_required
def add():
    cash_amount = request.form.get("amount")
    user_id = session["user_id"]
    max_add = 10000

    try:
        cash_amount = float(cash_amount)
    except:
        return apology("Invalid cash amount", 400)

    if cash_amount > max_add:
        return apology("Can't add more than $10000", 400)
    else:
        # add cash
        db.execute("update 'users' set cash=cash+{0} where id = {1}".format(cash_amount, user_id))
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
