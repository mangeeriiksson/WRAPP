from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import os
from werkzeug.utils import secure_filename
import sqlite3
import time
import subprocess
from datetime import datetime
import urllib.parse

# Flask-inställningar
app = Flask(__name__)
app.secret_key = 'utbildningsnyckel123'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
DATABASE = 'vulnerable.db'

# Anpassat filter för att formatera datum
@app.template_filter('date')
def format_date(value, format='%Y-%m-%d'):
    """Formatera ett datum."""
    if value == "now":
        value = datetime.now()
    return value.strftime(format)

# Initiera databas
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                image TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                profile_picture TEXT,
                bio TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT,
                FOREIGN KEY (product_id) REFERENCES products (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Kontrollera om email-kolumnen finns
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        if 'email' not in column_names:
            # Lägg till email-kolumnen med NULL-värden
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
            # Uppdatera alla rader med ett standardvärde för email
            cursor.execute("UPDATE users SET email = ''")
            # Ändra email-kolumnen till NOT NULL
            cursor.execute("ALTER TABLE users RENAME TO users_temp")

            # Ta bort users_temp om den redan existerar
            cursor.execute("DROP TABLE IF EXISTS users_temp")

            # Skapa en temporär tabell med den nya strukturen
            cursor.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    profile_picture TEXT,
                    bio TEXT
                )
            ''')
            # Kopiera data från den befintliga tabellen till den temporära tabellen
            cursor.execute('''
                INSERT INTO users (id, username, password, email, profile_picture, bio)
                SELECT id, username, password, email, profile_picture, bio FROM users_temp
            ''')
            # Ta bort den befintliga tabellen
            cursor.execute('DROP TABLE users_temp')

        if 'bio' not in column_names:
            # Lägg till bio-kolumnen med NULL-värden
            cursor.execute("ALTER TABLE users ADD COLUMN bio TEXT")
            # Uppdatera alla rader med ett standardvärde för bio
            cursor.execute("UPDATE users SET bio = ''")

        if 'profile_picture' not in column_names:
            # Lägg till profile_picture-kolumnen med NULL-värden
            cursor.execute("ALTER TABLE users ADD COLUMN profile_picture TEXT")
            # Uppdatera alla rader med ett standardvärde för profile_picture
            cursor.execute("UPDATE users SET profile_picture = ''")

        conn.commit()

# Kontrollera filtyp
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Startsida
@app.route('/')
def home():
    return render_template('home.html')

# Login och registrering
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        action = request.form.get('action')

        if action == 'login':
            query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                user = cursor.fetchone()
                if user:
                    session['user'] = username
                    session['cart'] = []
                    session['flags'] = session.get('flags', {})
                    flash(f'Välkommen {username}!', 'success')
                    if username == 'admin':
                        return redirect(url_for('admin'))
                    return redirect(url_for('shop'))
                else:
                    flash('Felaktigt användarnamn eller lösenord.', 'danger')

        elif action == 'register':
            email = request.form.get('email')
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", (username, password, email))
                    conn.commit()
                    flash('Registreringen lyckades! Logga in.', 'success')
                except sqlite3.IntegrityError:
                    flash('Användarnamnet eller e-postadressen är redan registrerad.', 'danger')
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Du har loggats ut.', 'info')
    return redirect(url_for('home'))

# Adminportal
@app.route('/admin')
def admin():
    if 'user' not in session or session['user'] != 'admin':
        flash('Du måste vara inloggad som admin för att komma åt adminportalen.', 'danger')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, password, email FROM users")
        users = cursor.fetchall()
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()

    return render_template('admin.html', users=users, products=products)

# Lägg till produkt
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user' not in session or session['user'] != 'admin':
        flash('Endast administratörer kan lägga till produkter.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description']
        file = request.files['image']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
        else:
            file_path = None

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (name, price, description, image)
                VALUES (?, ?, ?, ?)
            ''', (name, price, description, file_path))
            conn.commit()

        flash(f'Produkten "{name}" har lagts till.', 'success')
        return redirect(url_for('admin'))

    return render_template('add_product.html')

# Uppdatera produkt
@app.route('/update_product/<int:product_id>', methods=['GET', 'POST'])
def update_product(product_id):
    if 'user' not in session or session['user'] != 'admin':
        flash('Endast administratörer kan uppdatera produkter.', 'danger')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

        if not product:
            flash('Produkten finns inte.', 'danger')
            return redirect(url_for('admin'))

        if request.method == 'POST':
            name = request.form['name']
            price = request.form['price']
            description = request.form['description']
            file = request.files['image']

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
            else:
                file_path = product[4]  # Behåll den befintliga bildsökvägen

            cursor.execute('''
                UPDATE products
                SET name = ?, price = ?, description = ?, image = ?
                WHERE id = ?
            ''', (name, price, description, file_path, product_id))
            conn.commit()

            flash(f'Produkten "{name}" har uppdaterats.', 'success')
            return redirect(url_for('admin'))

    return render_template('update_product.html', product=product)

# Ta bort produkt
@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'user' not in session or session['user'] != 'admin':
        flash('Endast administratörer kan ta bort produkter.', 'danger')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()

    flash('Produkten har tagits bort.', 'success')
    return redirect(url_for('admin'))

# Shop
@app.route('/shop')
def shop():
    query = "SELECT * FROM products"
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        products = cursor.fetchall()
    return render_template('shop.html', products=products)

# Flaggor
@app.route('/flags')
def view_flags():
    flags = session.get('flags', {})
    return render_template('flags.html', flags=flags)

# Sätt flagga
@app.route('/set_flag/<string:flag_id>', methods=['POST'])
def set_flag(flag_id):
    flags = session.get('flags', {})
    flags[flag_id] = True
    session['flags'] = flags
    flash(f"Flaggan '{flag_id}' har låsts upp!", 'success')
    return redirect(url_for('view_flags'))

# Sökfunktion
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    filtered_query = query.replace("UNION", "").replace("SELECT", "")  # Enkel blacklisting
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM products WHERE name LIKE ?", ('%' + filtered_query + '%',))
        products = cursor.fetchall()
    flash(f"Sökresultat för: {query}", "info")
    return render_template('shop.html', products=products)

# Lägg till produkt i kundvagn
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        if product:
            session['cart'] = session.get('cart', [])
            session['cart'].append({
                'id': product[0],
                'name': product[1],
                'description': product[3],
                'price': product[2],
            })
            session.modified = True
            flash(f'{product[1]} har lagts till i kundvagnen.', 'success')
    return redirect(url_for('shop'))

# Ta bort produkt från kundvagn
@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    session['cart'] = [item for item in session.get('cart', []) if item['id'] != product_id]
    session.modified = True
    flash('Produkten har tagits bort från kundvagnen.', 'info')
    return redirect(url_for('view_cart'))

# Visa kundvagn
@app.route('/cart')
def view_cart():
    return render_template('cart.html', cart=session.get('cart', []))

# Töm kundvagn
@app.route('/empty_cart')
def empty_cart():
    session['cart'] = []
    session.modified = True
    flash('Kundvagnen har tömts.', 'info')
    return redirect(url_for('view_cart'))

# Slutför köp
@app.route('/checkout', methods=['POST'])
def checkout():
    with sqlite3.connect(DATABASE) as conn:
        cart = session.get('cart', [])
        if not cart:
            flash('Din kundvagn är tom.', 'danger')
            return redirect(url_for('shop'))

        total = sum(float(item['price']) for item in cart)
        user = session.get('user')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO orders (user, total, status) VALUES (?, ?, ?)", (user, total, 'Under behandling'))
        conn.commit()

        session['cart'] = []
        session.modified = True
        flash('Din order har lagts till och är under behandling.', 'success')
    return redirect(url_for('shop'))

# OS-kommandoinjektion
@app.route('/run_command', methods=['GET', 'POST'])
def run_command():
    result = None
    if request.method == 'POST':
        cmd = request.form.get('cmd')
        if cmd:
            result = subprocess.getoutput(cmd)  # OS Command Injection
    return render_template('command.html', result=result)

# Path Traversal
@app.route('/file_read', methods=['GET', 'POST'])
def file_read():
    content = None
    if request.method == 'POST':
        path = request.form.get('file_path')
        try:
            with open(path, 'r') as file:
                content = file.read()
        except Exception as e:
            content = f"Fel: {str(e)}"
    return render_template('file_read.html', content=content)

# Path Traversal with validation
@app.route('/file_read_validated', methods=['GET', 'POST'])
def file_read_validated():
    content = None
    if request.method == 'POST':
        path = request.form.get('file_path')
        if path.startswith('/valid/path/'):
            try:
                with open(path, 'r') as file:
                    content = file.read()
            except Exception as e:
                content = f"Fel: {str(e)}"
        else:
            content = "Ogiltig sökväg."
    return render_template('file_read_validated.html', content=content)

# Blind OS command injection with output redirection
@app.route('/blind_command', methods=['GET', 'POST'])
def blind_command():
    if request.method == 'POST':
        cmd = request.form.get('cmd')
        if cmd:
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            flash('Kommandot har körts.', 'success')
    return render_template('blind_command.html')

# Username enumeration via subtly different responses
@app.route('/check_username', methods=['GET'])
def check_username():
    username = request.args.get('username')
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
        user = cursor.fetchone()
        if user:
            return "Username exists", 200
        else:
            return "Username does not exist", 404

# Username enumeration via response timing
@app.route('/check_username_timing', methods=['GET'])
def check_username_timing():
    username = request.args.get('username')
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
        user = cursor.fetchone()
        if user:
            time.sleep(2)  # Simulates a delay to indicate that the username exists
        return "Checked", 200

# Brute-forcing a stay-logged-in cookie
@app.route('/set_cookie', methods=['GET'])
def set_cookie():
    username = request.args.get('username')
    response = make_response(redirect(url_for('home')))
    response.set_cookie('stay_logged_in', username)
    return response

@app.route('/check_cookie', methods=['GET'])
def check_cookie():
    username = request.cookies.get('stay_logged_in')
    if username:
        return f"Logged in as {username}", 200
    else:
        return "Not logged in", 404

# Password brute-force via password change
@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        username = request.form.get('username')
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM users WHERE username = '{username}' AND password = '{old_password}'")
            user = cursor.fetchone()
            if user:
                cursor.execute(f"UPDATE users SET password = '{new_password}' WHERE username = '{username}'")
                conn.commit()
                flash('Lösenordet har ändrats.', 'success')
            else:
                flash('Felaktigt användarnamn eller lösenord.', 'danger')
    return render_template('change_password.html')

# 2FA simple bypass
@app.route('/2fa', methods=['GET', 'POST'])
def two_factor_auth():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        two_factor_code = request.form.get('two_factor_code')
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'")
            user = cursor.fetchone()
            if user:
                # Bypass 2FA by always accepting the code
                session['user'] = username
                session['cart'] = []
                session['flags'] = session.get('flags', {})
                flash(f'Välkommen {username}!', 'success')
                return redirect(url_for('shop'))
            else:
                flash('Felaktigt användarnamn, lösenord eller 2FA-kod.', 'danger')
    return render_template('2fa.html')

# Användarprofiler
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        flash('Du måste vara inloggad för att komma åt din profil.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        bio = request.form.get('bio')
        file = request.files['profile_picture']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
        else:
            file_path = None

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET bio = ?, profile_picture = ? WHERE username = ?", (bio, file_path, session['user']))
            conn.commit()

        flash('Din profil har uppdaterats.', 'success')
        return redirect(url_for('profile'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT bio, profile_picture FROM users WHERE username = ?", (session['user'],))
        user_data = cursor.fetchone()

    return render_template('profile.html', bio=user_data[0], profile_picture=user_data[1])

# Initiera databas och starta server
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True)
