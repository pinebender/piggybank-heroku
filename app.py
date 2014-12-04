from flask import Flask, render_template, redirect, url_for, request, session, flash
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CsrfProtect
from flask_wtf import Form
from wtforms import TextField, IntegerField, BooleanField, PasswordField, HiddenField, validators, \
	TextAreaField, DateTimeField, DateField, DecimalField, SelectField
from wtforms.widgets import HiddenInput
from wtforms.validators import Required, EqualTo, Optional, Length, Email, NumberRange
from datetime import datetime, timedelta
from celery import Celery

app = Flask(__name__)
app.config.from_object("config")

csrf = CsrfProtect()
csrf.init_app(app)

db = SQLAlchemy(app)

celery = Celery(app)
celery.conf.add_defaults(app.config)


'''
### Celery Flask Integration
def make_celery(app):
    celery = Celery(app.import_name, broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery
celery = make_celery(app)
'''

### Login/Session Manager
class LoginManager:
	def login(self, user, password):
		session['userid'] = user.id
		session['sessionhash'] = generate_password_hash(user.username+str(user.id)) # change to user.email?
		return

	def logout(self):
		session.pop('userid', None)
		session.pop('sessionhash', None)
		return True

	def check_login(self, session):
		if 'userid' in session:
			user = User.query.get_or_404(session['userid'])
			if check_password_hash(session['sessionhash'], user.username+str(user.id)):
				return True
		return False

lm = LoginManager()

### DB Helper Class
class DBManager:

	def create_user(self, username, password, email, role, parent=None):
		pwhash = generate_password_hash(password)
		db.session.add(User(username.lower(), pwhash, email.lower(), role, parent))
		db.session.commit()
		return

	def get_user_by_id(self, userid):
		return User.query.get_or_404(userid)

	def create_bank(self, user, bankname):		
		db.session.add(PiggyBank(user, bankname))
		db.session.commit()
		return

	def delete_bank(self, bank):
		db.session.delete(bank)
		db.session.commit()
		return

	def rename_bank(self, bank, name):
		bank.name = name
		db.session.commit()
		return

	def create_deposit(self, amount, bank, description=None, date_deposited=None, source=None, source_id=None):
		db.session.add(Deposit(amount, bank, description, date_deposited, source, source_id))
		bank.current_balance += amount
		db.session.commit()
		return

	def delete_deposit(self, deposit):
		db.session.delete(deposit)
		db.session.commit()
		return

	def create_expense(self, name, price, bank, description=None, purchased=None, date_added=None, date_purchased=None, purchased_by=None):
		db.session.add(Expense(name, price, bank, description, purchased, date_added, date_purchased, purchased_by))
		if purchased == True:
			bank.current_balance -= price
		db.session.commit()
		return

	def delete_expense(self, expense):
		db.session.delete(expense)
		db.session.commit()
		return

	def purchase_expense(self, expense):
		expense.purchased = True
		expense.date_purchased = datetime.utcnow()
		expense.piggybank.current_balance -= expense.price
		db.session.commit()
		return

	def refund_expense(self, expense):
		if expense.purchased == True:
			expense.purchased = False
			expense.date_purchased = None
			expense.piggybank.current_balance += expense.price
			db.session.commit()
		return

	def create_allowance(self, amount, frequency, piggybank, description=None, payday=None, active=True):
		db.session.add(Allowance(amount, frequency, piggybank, description, payday, active))
		db.session.commit()
		return

	def toggle_allowance(self, allowance):
		if allowance.active == True:
			allowance.active = False
		else:
			allowance.active = True
		db.session.commit()
		return


	def change_allowance(self, allowance, amount, frequency, payday=None):
		allowance.amount = amount
		allowance.frequency = frequency
		allowance.payday = payday
		db.session.commit()
		return

	def delete_allowance(self, allowance):
		db.session.delete(allowance)
		db.session.commit()
		return

dbm = DBManager()

### Models
class User(db.Model):
	__tablename__ = 'user'
	id = db.Column(db.Integer, primary_key=True)
	username = db.Column(db.String(80), unique=True)
	password = db.Column(db.String(80))
	email = db.Column(db.String(120), unique=True)
	active = db.Column(db.Boolean, default=False)
	role = db.Column(db.String(80))
	
	parent_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	parent = db.relationship('User', backref='children', remote_side=[id])


	def __init__(self, username, password, email, role, parent = None):
		self.username = username
		self.password = password
		self.email = email
		self.active = True
		self.role = role
		if role == "child":
			self.parent = parent

	def __repr__(self):
		return '<User %r>' % self.username
	
class PiggyBank(db.Model):
	__tablename__ = 'piggybank'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(80))
	current_balance = db.Column(db.Numeric(10,2))
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	user = db.relationship('User', backref=db.backref('piggybanks', lazy='dynamic'))

	def __init__(self, user, name):
		self.current_balance = 0
		self.user = user
		self.name = name
	def __repr__(self):
		return '<PiggyBank %r>' % self.name

	def get_balance(self):
		return self.current_balance

class Allowance(db.Model):
	__tablename__ = 'allowance'
	id = db.Column(db.Integer, primary_key=True)
	amount = db.Column(db.Numeric(10,2))
	description = db.Column(db.String(80))
	frequency = db.Column(db.String(12))
	payday = db.Column(db.Integer)
	active = db.Column(db.Boolean, default=False)
	bank_id = db.Column(db.Integer, db.ForeignKey('piggybank.id'))
	piggybank = db.relationship('PiggyBank', backref=db.backref('allowances', lazy='dynamic'))

	def __init__(self, amount, frequency, piggybank, description=None, payday=None, active=True):
		self.amount = amount
		self.frequency = frequency
		self.piggybank = piggybank
		self.description = description
		self.active = active
		if payday == None:
			payday = 0
		self.payday = payday

	def __repr__(self): 
		return '<Allowance %r>' % self.id

class Deposit(db.Model): 
	__tablename__ = 'deposit'
	id = db.Column(db.Integer, primary_key=True)
	date_deposited  = db.Column(db.DateTime)
	amount_deposited = db.Column(db.Numeric(10,2))
	balance = db.Column(db.Numeric(10,2))
	source = db.Column(db.String(80)) # description for display on screen; use source_id if by a user, otherwise Allowance
	source_id = db.Column(db.Integer) #if deposit made by user
	description = db.Column(db.Text)
	bank_id = db.Column(db.Integer, db.ForeignKey('piggybank.id'))
	piggybank = db.relationship('PiggyBank', backref=db.backref('deposits', lazy='dynamic'))

	def __init__(self, amount_deposited, piggybank, description=None, date_deposited=None, source=None, source_id=None):
		self.amount_deposited = amount_deposited
		self.piggybank = piggybank
		if date_deposited == None:
			date_deposited = datetime.utcnow()
		self.date_deposited = date_deposited
		if description == None:
			description = ""
		self.description = description
		if source == None:
			source = piggybank.user.username
		self.source = source
		if source_id == None:
			source_id = piggybank.user_id
		self.source_id = source_id
		self.balance = piggybank.current_balance + self.amount_deposited

	def __repr__(self):
		return '<Deposit %r>' % self.date_deposited

class Expense(db.Model):
	__tablename__ = 'expense'
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(80))
	description = db.Column(db.Text)
	price = db.Column(db.Numeric(10,2))
	date_purchased = db.Column(db.DateTime)
	date_added = db.Column(db.DateTime)
	purchased = db.Column(db.Boolean, default=False)
	purchased_by = db.Column(db.Integer) #user id
	bank_id = db.Column(db.Integer, db.ForeignKey('piggybank.id'))
	piggybank = db.relationship('PiggyBank', backref=db.backref('expenses', lazy='dynamic'))

	def __init__(self, name, price, piggybank, description=None, purchased=True, date_added=None, date_purchased=None, purchased_by=None):
		self.name = name
		self.price = price
		self.piggybank = piggybank
		self.description = description
		if date_added == None:
			date_added = datetime.utcnow()
		self.date_added = date_added
		if purchased == True:
			self.purchased = True
		else:
			purchased = False
		if purchased == True:
			date_purchased = datetime.utcnow()
		self.date_purchased = date_purchased
		if purchased_by == None:
			purchased_by = self.id
		self.purchased_by = purchased_by

	def __repr__(self):
		return '<Expense %r>' % self.name

### Forms
class RegistrationForm(Form):
	username = TextField('Username', [validators.Length(min=4, max=25, message=("Username must be between 4 and 25 characters in length.")), validators.Required(), ])
	email = TextField('Email Address', [validators.Length(max=120), validators.Required()])
	password = PasswordField('Password', [validators.Length(min=6, message=("Password must be at least 6 characters long.")), validators.Required(), validators.EqualTo('verify', message='Password does not match confirmation. Please try again.')])
	verify = PasswordField('Confirm Password')

class LoginForm(Form):
	username = TextField('Username')
	password = PasswordField('Password')

class AddBankForm(Form):
	bankname = TextField('Name', [validators.Required(), validators.Length(min=1, max=80, message=("Name must be between 1 and 80 characters."))])

# AddDepositForm (for bank detail page)
class AddDepositForm(Form):
	amount = DecimalField('Amount', [validators.Required()])
	description = TextField('Description')


# AddExpenseForm
class AddExpenseForm(Form):
	name = TextField('Name', [validators.Required()])
	price = DecimalField('Price', [validators.Required()])
	description = TextField('Description')
	purchased = BooleanField('Purchase Now?')


# AddAllowanceForm - rename to AllowanceForm, use for editing allowances as well
class AddAllowanceForm(Form): 
	amount = DecimalField('Allowance Amount', [validators.Required()])
	frequency = SelectField("Frequency", choices=[("daily","Daily"), ("weekly", "Weekly"), ("biweekly", "Bi-Weekly"), ("monthly", "Monthly")] )
	description = TextField('Description')
	
class PayDayForm(Form):
	payday = SelectField("Pay On:", choices=[("0", "Monday"), ("1", "Tuesday"), ("2", "Wednesday"), ("3", "Thursday"), ("4", "Friday"), ("5", "Saturday"), ("6", "Sunday")])

class BankIdForm(Form):
	bankid = IntegerField('BankID', [validators.NumberRange(min=0)], widget=HiddenInput())

class BankDeleteForm(Form):
	bankid = IntegerField('BankID', [validators.NumberRange(min=0)], widget=HiddenInput())
	password = PasswordField('Confirm Password')

class BankRenameForm(Form):
	bankid = IntegerField('BankID', widget=HiddenInput())
	bankname = TextField('Bank Name', [validators.Length(min=1, max=80, message=("Name must be between 1 and 80 characters."))])

class DepositIdForm(Form):
	depositid = IntegerField('DepositID', [validators.NumberRange(min=0)], widget=HiddenInput())

class ExpenseIdForm(Form):
	expenseid = IntegerField('ExpenseID', [validators.NumberRange(min=0)], widget=HiddenInput())

class AllowanceIdForm(Form):
	allowanceid = IntegerField('AllowanceID', [validators.NumberRange(min=0)], widget=HiddenInput())

class UserIdForm(Form):
	userid = IntegerField('UserID', [validators.NumberRange(min=0)], widget=HiddenInput())


### Views/Controllers
@app.route('/', methods=['GET', 'POST'])
def front():
	if lm.check_login(session):
		return redirect(url_for('home'))
	login_form = LoginForm(request.form)
	registration_form = RegistrationForm(request.form)
	return render_template('front.html', loginform=login_form, regform=registration_form, regretry=False)

@app.route('/login/', methods=['GET', 'POST'])
def login():
	login_form = LoginForm(request.form)
	registration_form = RegistrationForm(request.form)
	if lm.check_login(session):
		return redirect(url_for('home'))

	if request.method == 'POST':
		if login_form.validate():
			user = User.query.filter_by(username = login_form.username.data.lower()).first()
			if user:
				if check_password_hash(user.password, login_form.password.data) == True: 
					lm.login(user, login_form.password.data)
					return redirect(url_for('home'))
				else:
					login_form.password.errors.append("Login failed. Please try again.")					
			else:
				login_form.username.errors.append("Login failed. Please try again.")
			
	return render_template('front.html', loginform=login_form, regform=registration_form, regretry=False)

@app.route('/register/', methods=['GET', 'POST'])
def register():
	registration_form = RegistrationForm(request.form)
	login_form = LoginForm(request.form)
	retry = False
	if lm.check_login(session):
		return redirect(url_for('home'))

	if request.method == 'POST':
		if registration_form.validate():
			# check that username and email are unique
			userquery = User.query.filter_by(username=registration_form.username.data.lower()).first()
			if userquery != None and registration_form.username.data.lower() == userquery.username:
				registration_form.username.errors.append("Username is already in use. Please choose another.")
				retry = True

			emailquery = User.query.filter_by(email=registration_form.email.data.lower()).first()
			if emailquery != None and registration_form.email.data.lower() == emailquery.email:
				registration_form.email.errors.append("Email address is already in use. Please choose another.")
				retry = True
			
			if registration_form.password.data != registration_form.verify.data:
				# error displayed via form validation
				retry = True
			
			if retry == False:
				# create user, log in, and redirect
				dbm.create_user(registration_form.username.data, registration_form.password.data, registration_form.email.data, "parent")
				user = User.query.filter_by(username = registration_form.username.data.lower()).first()
				lm.login(user, registration_form.password.data)
				return redirect(url_for('home'))

	return render_template('front.html', regform=registration_form, loginform=login_form, regretry=retry)


@app.route('/home/', methods=['GET', 'POST'])
def home():
	addallowanceform = AddAllowanceForm(request.form)
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])	
		return render_template('home.html', username=user.username, role=user.role, addallowanceform=addallowanceform)
	return redirect(url_for('login'))

@csrf.exempt
@app.route('/navigation/', methods=['GET', 'POST'])
def navigationbar():
	if lm.check_login(session):
	 	bankid = request.form['bankid']
	 	bank = PiggyBank.query.get_or_404(bankid)
	 	if request.method == 'POST':
	 		return render_template('navigationbar.html', bankid=bankid, bank=bank)
	return render_template('navigationbar.html')

@csrf.exempt
@app.route('/banks/', methods=['GET', 'POST'])
def banks():
	addbankform = AddBankForm(request.form)
	bankidform = BankIdForm(request.form)
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		piggybanks = user.piggybanks.order_by(PiggyBank.id).all()
		return render_template('banks.html', addbankform=addbankform, bankidform=bankidform, piggybanks=piggybanks)
	return render_template('oops.html')

# create bank
@app.route('/addbank/', methods=['GET', 'POST'])
def add_bank():
	if lm.check_login(session):
		form = AddBankForm(request.form)
		user = dbm.get_user_by_id(session['userid'])
		if request.method == 'POST':
			if form.validate():
				dbm.create_bank(user, form.bankname.data)
				return redirect(url_for('banks'))
	return render_template('oops.html')


@csrf.exempt
@app.route('/overview/', methods=['GET', 'POST'])
def overview():
	if lm.check_login(session):
		bankid = request.form['bankid']
		user = dbm.get_user_by_id(session['userid'])
		if request.method == 'POST':
			piggybank = PiggyBank.query.get_or_404(bankid)
			recent_purchases = piggybank.expenses.filter(Expense.purchased == True).order_by(desc(Expense.date_purchased)).limit(5).all()
			recent_deposits = piggybank.deposits.order_by(desc(Deposit.date_deposited)).limit(5).all()
			return render_template('overview.html', bank=piggybank, recentpurchases=recent_purchases, recentdeposits=recent_deposits)
	return render_template('overview.html')

@csrf.exempt
@app.route('/deposits/', methods=['GET', 'POST'])
def deposits():
	add_deposit_form = AddDepositForm(request.form)
	bank_id_form = BankIdForm(request.form)
	deposit_id_form = DepositIdForm(request.form)
	if lm.check_login(session):
		bankid = request.form['bankid']
		bank = PiggyBank.query.get_or_404(bankid)
		if request.method =='POST':
			return render_template('deposits.html', bank=bank, adddepositform=add_deposit_form, bankidform=bank_id_form, depositidform=deposit_id_form)
	return render_template('oops.html')

# create deposit
@csrf.exempt
@app.route('/adddeposit/', methods=['GET', 'POST'])
def add_deposit():

	#bankid = piggybank.id
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_deposit_form = AddDepositForm(request.form)
		bank_id_form = BankIdForm(request.form)
		deposit_id_form=DepositIdForm(request.form)
		piggybank = PiggyBank.query.get_or_404(bank_id_form.bankid.data)
		if request.method == 'POST':
			if add_deposit_form.validate() and bank_id_form.validate():
				if piggybank.user_id == user.id:
					dbm.create_deposit(add_deposit_form.amount.data, piggybank, add_deposit_form.description.data)
					return render_template('deposits.html', bank=piggybank, adddepositform=add_deposit_form, bankidform=bank_id_form, depositidform=deposit_id_form)
	return render_template('oops.html')

# delete deposit
@csrf.exempt
@app.route('/deletedeposit/', methods=['GET', 'POST'])
def delete_deposit():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_deposit_form = AddDepositForm(request.form)
		bank_id_form = BankIdForm(request.form)
		deposit_id_form = DepositIdForm(request.form)
		if request.method == 'POST':
			deposit = Deposit.query.get_or_404(deposit_id_form.depositid.data)
			piggybank = deposit.piggybank
			if deposit.piggybank.user_id == user.id:
				dbm.delete_deposit(deposit)
				return render_template('deposits.html', bank=piggybank, adddepositform=add_deposit_form, bankidform=bank_id_form, depositidform=deposit_id_form)
	return render_template('oops.html')


@csrf.exempt
@app.route('/expenses/', methods=['GET', 'POST'])
def expenses():
	add_expense_form = AddExpenseForm(request.form)
	bank_id_form = BankIdForm(request.form)
	expense_id_form = ExpenseIdForm(request.form)
	if lm.check_login(session):
		bankid = request.form['bankid']
		piggybank = PiggyBank.query.get_or_404(bankid)
		if request.method =='POST':
			return render_template('expenses.html', bank=piggybank, addexpenseform=add_expense_form, bankidform=bank_id_form, expenseidform = expense_id_form)
	return render_template('oops.html')

# add expense
@app.route('/addexpense/', methods=['GET', 'POST'])
def add_expense():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_expense_form = AddExpenseForm(request.form)
		bank_id_form = BankIdForm(request.form)
		expense_id_form = ExpenseIdForm(request.form)
		piggybank = PiggyBank.query.get_or_404(bank_id_form.bankid.data)
		if request.method == 'POST':
			if add_expense_form.validate() and bank_id_form.validate():
				if piggybank.user_id == user.id:
					purchased = False
					if add_expense_form.purchased.data:
						purchased = True
					dbm.create_expense(add_expense_form.name.data, add_expense_form.price.data, piggybank, add_expense_form.description.data, purchased )
					return render_template('expenses.html', bank=piggybank, addexpenseform=add_expense_form, bankidform=bank_id_form, expenseidform=expense_id_form)
	return render_template('oops.html')

# purchase expense
@csrf.exempt
@app.route('/purchaseexpense/', methods=['GET', 'POST'])
def purchase_expense():
	expense_id_form = ExpenseIdForm(request.form)
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_expense_form = AddExpenseForm(request.form)
		bank_id_form = BankIdForm(request.form)
		expense_id_form = ExpenseIdForm(request.form)
		if request.method == 'POST':
			expense = Expense.query.get_or_404(expense_id_form.expenseid.data)
			piggybank = expense.piggybank
			if expense.piggybank.user_id == user.id:
				dbm.purchase_expense(expense)
				return render_template('expenses.html', bank=piggybank, addexpenseform=add_expense_form, bankidform=bank_id_form, expenseidform=expense_id_form)
	return render_template('oops.html')



# delete expense
@csrf.exempt
@app.route('/deleteexpense/', methods=['GET', 'POST'])
def delete_expense():
	expense_id_form = ExpenseIdForm(request.form)
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_expense_form = AddExpenseForm(request.form)
		bank_id_form = BankIdForm(request.form)
		expense_id_form = ExpenseIdForm(request.form)
		if request.method == 'POST':
			expense = Expense.query.get_or_404(expense_id_form.expenseid.data)
			piggybank = expense.piggybank
			if expense.piggybank.user_id == user.id:
				dbm.delete_expense(expense)
				return render_template('expenses.html', bank=piggybank, addexpenseform=add_expense_form, bankidform=bank_id_form, expenseidform=expense_id_form)
	return render_template('oops.html')

# refund expense
@csrf.exempt
@app.route('/refundexpense/', methods=['GET', 'POST'])
def refund_expense():
	expense_id_form = ExpenseIdForm(request.form)
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_expense_form = AddExpenseForm(request.form)
		bank_id_form = BankIdForm(request.form)
		expense_id_form = ExpenseIdForm(request.form)
		if request.method =='POST':
			expense = Expense.query.get_or_404(expense_id_form.expenseid.data)
			piggybank = expense.piggybank
			if piggybank.user_id == user.id:
				dbm.refund_expense(expense)
				return render_template('expenses.html', bank=piggybank, addexpenseform=add_expense_form, bankidform=bank_id_form, expenseidform=expense_id_form)
	return render_template('oops.html')


@csrf.exempt
@app.route('/allowances/', methods=['GET', 'POST'])
def allowances():
	add_allowance_form = AddAllowanceForm(request.form)
	bank_id_form = BankIdForm(request.form)
	allowance_id_form = AllowanceIdForm(request.form)
	if lm.check_login(session):
		bankid = request.form['bankid']
		bank = PiggyBank.query.get_or_404(bankid)
		if request.method=='POST':
			return render_template('allowances.html', bank=bank, addallowanceform=add_allowance_form, bankidform=bank_id_form, allowanceidform=allowance_id_form)
		return render_template('allowances.html')

# add allowance
@ app.route('/addallowance/', methods=['GET', 'POST'])
def add_allowance():	
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		add_allowance_form = AddAllowanceForm(request.form)
		bank_id_form = BankIdForm(request.form)
		allowance_id_form = AllowanceIdForm(request.form)
		piggybank = PiggyBank.query.get_or_404(bank_id_form.bankid.data)
		if request.method == 'POST' and add_allowance_form.validate() and bank_id_form.validate():
			if piggybank.user_id == user.id:
				dbm.create_allowance(add_allowance_form.amount.data, add_allowance_form.frequency.data, piggybank, \
				 add_allowance_form.description.data)
				return render_template('allowances.html', bank=piggybank, addallowanceform=add_allowance_form, bankidform=bank_id_form, allowanceidform=allowance_id_form)
	return render_template('oops.html')

@app.route('/updateallowance/', methods=['GET', 'POST'])
def update_allowance():
	allowance_form = AddAllowanceForm(request.form)
	allowance_id_form = AllowanceIdForm(request.form)
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		if request.method =='POST' and allowance_form.validate():
			allowance = Allowance.query.get_or_404(allowance_id_form.allowanceid.data)
			if allowance.piggypank.user_id == user.id:
				dbm.change_allowance(allowance_form.amount.data, allowance_form.frequency.data, allowance_form.description.data)
	return redirect(url_for('home'))

@csrf.exempt
@app.route('/toggleallowance/', methods=['GET', 'POST'])
def toggle_allowance():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		allowance_id_form = AllowanceIdForm(request.form)
		add_allowance_form = AddAllowanceForm(request.form)
		bank_id_form = BankIdForm(request.form)
		if request.method == 'POST':
			allowance = Allowance.query.get_or_404(allowance_id_form.allowanceid.data)
			piggybank = allowance.piggybank
			if piggybank.user_id == user.id:
				dbm.toggle_allowance(allowance)
				return render_template('allowances.html', bank=piggybank, addallowanceform=add_allowance_form, bankidform=bank_id_form, allowanceidform=allowance_id_form)
	return render_template('oops.html')

# delete allowance
@csrf.exempt
@app.route('/deleteallowance/', methods=['GET', 'POST'])
def delete_allowance():	
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		allowance_id_form = AllowanceIdForm(request.form)
		add_allowance_form = AddAllowanceForm(request.form)
		bank_id_form = BankIdForm(request.form)
		if request.method == 'POST':
			allowance = Allowance.query.get_or_404(allowance_id_form.allowanceid.data)
			piggybank = allowance.piggybank
			if allowance.piggybank.user_id == user.id:
				dbm.delete_allowance(allowance)
				return render_template('allowances.html', bank=piggybank, addallowanceform=add_allowance_form, bankidform=bank_id_form, allowanceidform=allowance_id_form)
	return render_template('oops.html')


@csrf.exempt
@app.route('/settings/', methods=['GET', 'POST'])
def settings():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		bankid = request.form['bankid']
		bank = PiggyBank.query.get_or_404(bankid)
		bank_delete_form = BankDeleteForm(request.form)
		bank_rename_form = BankRenameForm(request.form)
		if request.method == 'POST':
			return render_template('settings.html', bank=bank, bankdeleteform=bank_delete_form, bankrenameform=bank_rename_form)
	return render_template('oops.html')

@csrf.exempt
@app.route('/renamebank/', methods=['GET', 'POST'])
def rename_bank():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		bank_rename_form = BankRenameForm(request.form)
		bank_delete_form = BankDeleteForm(request.form)
		bank = PiggyBank.query.get_or_404(bank_rename_form.bankid.data)
		if request.method == 'POST' and bank_rename_form.validate():
			if bank.user_id == user.id:
				dbm.rename_bank(bank, bank_rename_form.bankname.data)
	return render_template('settings.html', bank=bank, bankrenameform=bank_rename_form, bankdeleteform=bank_delete_form)

# delete bank
@csrf.exempt
@app.route('/deletebank/', methods=['GET', 'POST'])
def delete_bank():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
		bank_delete_form = BankDeleteForm(request.form)
		bank_rename_form = BankRenameForm(request.form)
		bank = PiggyBank.query.get_or_404(bank_delete_form.bankid.data)	
		if request.method == 'POST':
			if bank.user_id == user.id and check_password_hash(user.password, bank_delete_form.password.data) == True:
				for allowance in bank.allowances:
					dbm.delete_allowance(allowance)
				for expense in bank.expenses:
					dbm.delete_expense(expense)
				for deposit in bank.deposits:
					dbm.delete_deposit(deposit)
				dbm.delete_bank(bank)
				return "Bank Deleted! Please select a different bank."
			elif bank.user_id == user.id and check_password_hash(user.password, bank_delete_form.password.data) != True:
				templist = list(bank_delete_form.password.errors)
				templist.append("Incorrect Password.")
				bank_delete_form.password.errors = tuple(templist)
	return render_template('settings.html', bank=bank, bankdeleteform=bank_delete_form, bankrenameform=bank_rename_form)




@app.route('/logout/')
def logout():
	if lm.check_login(session):
		lm.logout()
		
	return redirect(url_for('login'))


### Admin and Debug
@app.route('/admin/', methods=['GET', 'POST'])
def admin():

	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
	else: 
		return redirect(url_for('login'))

	if user.role == "admin":
		try:
			users = User.query.all()
		except:
			users = None
		return render_template('admin.html', username=user.username, users=users, role=user.role)

	return redirect(url_for('home'))

@app.route('/admin/reset_db/')
def reset_db():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
	if user.role == "admin":
		db.session.commit()
		db.drop_all()
		db.create_all()
		dbm.create_user("Admin", "testpass", "admin@piggy-bank.us", "admin")
		user = User.query.filter_by(username="admin").first()
		dbm.create_bank(user, "Test Bank")
		bank = PiggyBank.query.filter_by(user_id=user.id).first()
		dbm.create_allowance("10.00", "daily", bank)
		lm.login(user, "testpass")

	return redirect(url_for('admin'))

@app.route('/admin/generate_test_users/')
def generate_test_users():
	if lm.check_login(session):
		user = dbm.get_user_by_id(session['userid'])
	if user.role == "admin":
		try:
			dbm.create_user("testuser1", "testpass", "testemail1", "parent")
			dbm.create_user("testuser2", "testpass", "testemail2", "parent")
			dbm.create_user("testuser3", "testpass", "testemail3", "parent")
		except:
			pass
	return redirect(url_for('admin'))

### Tasks
@celery.task
def pay_allowances():
	date = datetime.utcnow().day
	day = datetime.utcnow().weekday()
	allowances = Allowance.query.all()
	for allowance in allowances:
		if allowance.active == True and allowance.piggybank != None:
			if (allowance.frequency == "daily") or (allowance.frequency == "weekly" and allowance.payday == day) \
			 or (allowance.frequency == "biweekly" and (date == 1 or date == 15)) \
			 or (allowance.frequency == "monthly" and date == 1):
				dbm.create_deposit(allowance.amount, allowance.piggybank, allowance.description)
	return


'''
@csrf.error_handler
def csrf_error(reason):
    return render_template('csrf_error.html', reason=reason), 400
'''


### run debug server
if __name__ == '__main__':
	
	app.debug = True
	app.run(host='0.0.0.0')