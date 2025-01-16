from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, abort
import os
from werkzeug.utils import secure_filename
import sqlite3
import uuid
import subprocess
from datetime import datetime
import logging


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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_ids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        ''')
        conn.commit()

# Kontrollera filtyp
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Startsida
@app.route('/')
def home():
    user = session.get('user')  # Hämta användare från sessionen
    return render_template('home.html', user=user)

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
    session.pop('user', None)  # Ta bort användaren från sessionen
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

@app.route('/add_product', methods=['POST'])
def add_product():
    try:
        name = request.form.get('name')
        price = request.form.get('price')
        description = request.form.get('description')
        file = request.files.get('image')
        file_path = None

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO products (name, price, description, image) VALUES (?, ?, ?, ?)",
                (name, price, description, file_path)
            )
            conn.commit()
            flash('Produkten har lagts till.', 'success')
    except Exception as e:
        flash(f"Ett fel uppstod: {str(e)}", 'danger')
        app.logger.error(f"Error: {str(e)}")
    return redirect(url_for('product'))

# Lägg till produkt i kundvagnen
@app.route('/add_to_cart/<int:product_id>', methods=['GET'])
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = []

    # Hämta produktinformation från databasen
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()

    if product:
        # Lägg till produkten i kundvagnen
        session['cart'].append({
            'id': product[0],
            'name': product[1],
            'price': product[2],
            'quantity': 1  # Du kan justera kvantiteten här om det behövs
        })
        session.modified = True
        flash(f'{product[1]} har lagts till i kundvagnen.', 'success')
        print(f"Produkt läggs till i kundvagnen: {session['cart']}")  # Debug-utskrift
    else:
        flash('Produkten kunde inte hittas.', 'danger')

    return redirect(url_for('shop'))

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

# Shop-sida
@app.route('/shop')
def shop():
    try:
        query = "SELECT * FROM products"
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            products = cursor.fetchall()
            print(f"Products fetched: {products}")  # Debug
    except sqlite3.Error as e:
        flash("Error fetching products from the database.", "danger")
        products = []

    # Kontrollera om produkter finns
    if not products:
        flash("Inga produkter tillgängliga just nu.", "info")

    return render_template('shop.html', products=products)

# Orderstatus
@app.route('/order_status', methods=['GET', 'POST'])
def order_status():
    order_id = None
    result = None
    error = None
    user_orders = []

    # Kontrollera om användaren är inloggad
    if 'user' in session:  # Kontrollera om 'user' finns i sessionen
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            # Hämta alla ordrar för den inloggade användaren
            cursor.execute("SELECT * FROM orders WHERE user = ?", (session['user'],))
            user_orders = cursor.fetchall()

    if request.method == 'POST':
        order_id = request.form.get('order_id')
        if order_id:
            try:
                # Kör ett osäkert kommando med användarinmatning
                command = f"echo 'Checking status for Order ID: {order_id}'"
                print(f"Running command: {command}")  # Logga kommandot för felsökning
                result = subprocess.check_output(command, shell=True, text=True)
            except subprocess.CalledProcessError as e:
                error = e.output

    # Rendera mallen och skicka med data
    return render_template(
        'order_status.html',
        order_id=order_id,
        result=result,
        error=error,
        user_orders=user_orders
    )

# OS Command with output redirection
@app.route('/save_order_status')
def save_order_status():
    # Get the 'order_id' parameter from the query string
    order_id = request.args.get('order_id')
    if order_id:
        try:
            # Unsafe command construction with output redirection vulnerability
            output_file = "order_status.txt"
            command = f"echo 'Order ID: {order_id} processed successfully' > {output_file}"
            subprocess.check_output(command, shell=True, text=True)
            return f"""
<h1>Order Status Saved</h1>
<p>The order status has been saved to <code>{output_file}</code>.</p>
<p>You can inject commands to see their effects. Example:</p>
<code>?order_id=1234;whoami >> {output_file}</code>
            """
        except subprocess.CalledProcessError as e:
            return f"Error: {e.output}"
    return """
<h1>Save Order Status</h1>
<p>Provide an order ID to save the status to the server.</p>
<p>Example: <code>?order_id=1234</code></p>
    """

@app.route('/vulnerable_file')
def vulnerable_file():
    # Get the 'filename' parameter from the query string
    filename = request.args.get('filename')
    file_content = None
    error_message = None

    if filename:
        try:
            # Use the full path provided by the user
            file_path = os.path.normpath(filename)

            # Check if the file exists and serve it
            if os.path.isfile(file_path):
                with open(file_path, 'r') as file:
                    file_content = file.read()
            else:
                error_message = "File not found."
        except Exception as e:
            error_message = f"Error: {str(e)}"

    # Render the template with the provided data
    return render_template(
        'product.html',
        filename=filename,
        file_content=file_content,
        error_message=error_message
    )

@app.route('/runcommand')
def runcommand():
    command = request.args.get('command')

    # Kör kommandot på servern
    try:
        result = os.popen(command).read()
        return result
    except Exception as e:
        abort(500, description=str(e))

@app.route('/blindcommand')
def blindcommand():
    command = request.args.get('command')

    # Kör kommandot på servern och omdirigera utdata till en fil
    try:
        os.system(f"{command} > /tmp/command_output.txt 2>&1")
        return "Command executed successfully"
    except Exception as e:
        abort(500, description=str(e))

# Definiera en vitlista av tillåtna filer
allowed_files = ['file1.txt', 'file2.txt']

@app.route('/readfile')
def readfile():
    filename = request.args.get('file')

    # Validera filnamnet
    if not filename or '../' in filename or filename.startswith('/'):
        abort(400, description="Invalid file path")

    # Kontrollera att filnamnet finns i vitlistan
    if filename not in allowed_files:
        abort(400, description="Invalid file path")

    # Bygg en säker filväg
    safe_path = os.path.join('allowed_directory', filename)

    try:
        with open(safe_path, 'r') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        abort(404, description="File not found")
    except Exception as e:
        abort(500, description=str(e))

# Användarprofiler
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    print("Profile route registered")  # Debug statement
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

# Funktion för att hämta order-ID:n
def get_orders():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM order_ids")
        orders = cursor.fetchall()
        for order in orders:
            print(order)

# Kör funktionen
get_orders()

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
    try:
        cart = session.get('cart', [])
        total_price = sum(float(item.get('price', 0)) * int(item.get('quantity', 0)) for item in cart)
        if not cart:
            flash('Din kundvagn är tom.', 'info')
        return render_template('cart.html', cart=cart, total_price=total_price)
    except Exception as e:
        flash(f"Ett fel uppstod: {str(e)}", 'danger')
        return redirect(url_for('home'))
@app.route('/empty_cart')
def empty_cart():
    session['cart'] = []
    session.modified = True
    flash('Kundvagnen är tömd.', 'info')
    return redirect(url_for('view_cart'))

# Slutför köp
@app.route('/checkout', methods=['POST'])
def checkout():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cart = session.get('cart', [])
            if not cart:
                flash('Din kundvagn är tom.', 'danger')
                return redirect(url_for('shop'))

            user = session.get('user')
            if not user:
                flash('Du måste vara inloggad för att slutföra köpet.', 'danger')
                return redirect(url_for('login'))

            total = sum(float(item.get('price', 0)) for item in cart)  # Säkerställ float
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO orders (user, total, status) VALUES (?, ?, ?)",
                (user, total, 'Under behandling')
            )
            conn.commit()

            session['cart'] = []
            session.modified = True
            flash('Din order har lagts till och är under behandling.', 'success')
    except sqlite3.Error as e:
        app.logger.error(f"Database error: {e}")
        flash(f"Database error: {str(e)}", 'danger')
    return redirect(url_for('shop'))

@app.route('/order_confirmation/<order_id>')
def order_confirmation(order_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            flash('Ordern kunde inte hittas.', 'danger')
            return redirect(url_for('shop'))

    return render_template('order_confirmation.html', order=order)

@app.route('/product')
def product():
    # Get the 'filename' parameter from the query string
    filename = request.args.get('filename')
    file_content = None
    error_message = None

    # Query the database for product information
    query = "SELECT id, name, description, price FROM products"
    products = []

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            products = cursor.fetchall()
    except Exception as e:
        error_message = f"Database error: {str(e)}"

    if filename:
        try:
            # Use the full path provided by the user
            file_path = os.path.normpath(filename)
            # Restrict file access to a specific directory
            allowed_directory = os.path.abspath('static/images/products')
            requested_file = os.path.abspath(file_path)

            # Check if the requested file is within the allowed directory
            if requested_file.startswith(allowed_directory):
                # Serve the file if it exists
                if os.path.isfile(requested_file):
                    return send_file(requested_file)
                else:
                    error_message = "File not found."
            else:
                # If traversal attempts to escape the allowed directory
                if "/etc/passwd" in requested_file:
                    file_content = """
                    root:x:0:0:root:/root:/bin/bash
                    user:x:1000:1000:user:/home/user:/bin/bash
                    guest:x:2000:2000:guest:/home/guest:/bin/bash
                    """
                else:
                    error_message = "Access denied. Forbidden path."
        except Exception as e:
            error_message = f"Error: {str(e)}"

    # Render the template with the provided data
    return render_template(
        'product.html',
        products=products,
        filename=filename,
        file_content=file_content,
        error_message=error_message
    )

# Mina ordrar
@app.route('/my_orders')
def my_orders():
    if 'user' not in session:
        flash('Du måste vara inloggad för att se dina order.', 'danger')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE user = ?", (session['user'],))
        orders = cursor.fetchall()

    return render_template('my_orders.html', orders=orders)

# Initiera databas och starta server
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True)
