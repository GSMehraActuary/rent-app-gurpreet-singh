from flask import Flask, render_template, request, redirect
import mysql.connector
from functools import wraps
from flask import Response

app = Flask(__name__)

# --- CONFIGURATION ---
DB_CONFIG = {
    'host': 'rent-app-gurpreet-singh-rent-app-gurpreet-singh.l.aivencloud.com',
    'port': 18143,
    'user': 'avnadmin',
    'password': 'AVNS_GSJlvWTTYMBsoWlB537',  # <--- PASTE YOUR PASSWORD HERE AGAIN
    'database': 'defaultdb',
    'ssl_disabled': False
}

def get_db_connection():
    return mysql.connector.connect(
        **DB_CONFIG,
        auth_plugin='mysql_native_password',
        ssl_verify_identity=False,
        ssl_ca=''
    )

# --- ROUTE 1: The Input Page ---
@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True) # dictionary=True lets us use tenant['name']
    
    # Get tenants to populate the dropdown menu
    cursor.execute("SELECT * FROM tenants")
    tenants = cursor.fetchall()
    
    conn.close()
    return render_template('staff.html', tenants=tenants)

# --- ROUTE 2: Handling the "Save" Click ---
@app.route('/submit-reading', methods=['POST'])
def submit_reading():
    # 1. Get data from the HTML form
    tenant_id = request.form['tenant_id']
    date = request.form['reading_date']
    reading = request.form['reading_value']

    # 2. Save it to the database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = "INSERT INTO meter_readings (tenant_id, reading_date, reading_value) VALUES (%s, %s, %s)"
        cursor.execute(query, (tenant_id, date, reading))
        conn.commit() # Don't forget this! It saves the changes.
        msg = "Success! Reading Saved."
    except mysql.connector.Error as err:
        msg = f"Error: {err}"
        
    conn.close()
    
    # 3. Go back to home page (or show success)
    return f"<h1>{msg}</h1><a href='/'>Back</a>"


# --- SECURITY: The Bouncer ---
def check_auth(username, password):
    # CHANGE THIS to your desired login!
    return username == 'admin' and password == 'rent123'

def authenticate():
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- ROUTE 3: The Admin Dashboard (Protected) ---
# --- ROUTE: The Super Admin Dashboard ---
import urllib.parse  # Make sure this is imported at the top

# --- ROUTE: The Super Admin Dashboard (Merged Version) ---
@app.route('/admin')
@requires_auth
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get all tenants
    cursor.execute("SELECT * FROM tenants")
    tenants = cursor.fetchall()
    
    report_data = []
    
    for t in tenants:
        # 2. Get last 2 readings for this tenant
        cursor.execute("SELECT * FROM meter_readings WHERE tenant_id = %s ORDER BY reading_date DESC LIMIT 2", (t['id'],))
        readings = cursor.fetchall()
        
        # Default values if data is missing
        bill_status = "No Data"
        whatsapp_url = "#"
        total_amt = 0
        
        if len(readings) >= 2:
            curr = readings[0]
            prev = readings[1]
            
            # --- THE CALCULATION LOGIC HAPPENS HERE ---
            units = curr['reading_value'] - prev['reading_value']
            elec_bill = units * 8
            
            # The "W-1442" Cleaning Fee Logic
            cleaning = 100 if t['address'] == 'W-1442' else 0
            
            total_amt = elec_bill + t['base_rent'] + cleaning
            bill_status = f"₹{total_amt}"
            
            # --- GENERATING THE MESSAGE ---
            # This replicates your "RentCalculationSender.py" format exactly
            msg = (f"{curr['reading_date']}\n"
                   f"*{t['name']}*\n"
                   f"Units: {curr['reading_value']} - {prev['reading_value']} = {units} kWh\n"
                   f"Elec Bill: {units} x 8 = ₹{elec_bill}\n"
                   f"Rent: ₹{t['base_rent']}\n")
            
            if cleaning > 0:
                msg += f"Total Amount = Electricity Bill + Rent + 100 for Cleaning = *₹{total_amt}*"
            else:
                msg += f"Total Amount = Electricity Bill + Rent = *₹{total_amt}*"
            
            # # Create the link (Sends to YOU first, so you can forward it)
            # # We use the tenant's phone number here
            # whatsapp_url = f"https://wa.me/91{t['phone']}?text={urllib.parse.quote(msg)}"

            # --- SAFE PHONE NUMBER LOGIC ---
            # 1. Get the phone from DB (e.g., "919871628696" or "9871628696")
            raw_phone = str(t['phone']).strip()
            
            # 2. If it doesn't start with 91, add it. If it does, leave it alone.
            if not raw_phone.startswith('91'):
                final_phone = "91" + raw_phone
            else:
                final_phone = raw_phone

            # 3. Create the link with the CLEAN phone number
            whatsapp_url = f"https://wa.me/{final_phone}?text={urllib.parse.quote(msg)}"
            
        elif len(readings) == 1:
            bill_status = "Need 1 more reading"
            
        # Combine everything into one object to send to HTML
        report_data.append({
            'id': t['id'],
            'name': t['name'],
            'address': t['address'],
            'phone': t['phone'],
            'base_rent': t['base_rent'], # Ensure this matches your HTML variable
            'status': bill_status,
            'whatsapp_link': whatsapp_url
        })
        
    conn.close()
    return render_template('admin.html', tenants=report_data)

# --- ROUTE 4: The Edit Page (View the Form) ---
@app.route('/edit-tenant/<int:id>', methods=['GET', 'POST'])
@requires_auth
def edit_tenant(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        # Update the database with new info
        name = request.form['name']
        rent = request.form['base_rent']
        phone = request.form['phone']
        
        cursor.execute("""
            UPDATE tenants 
            SET name = %s, base_rent = %s, phone = %s 
            WHERE id = %s
        """, (name, rent, phone, id))
        conn.commit()
        conn.close()
        return redirect('/admin') # Go back to dashboard after saving

    # If GET, show the current info so you can edit it
    cursor.execute("SELECT * FROM tenants WHERE id = %s", (id,))
    tenant = cursor.fetchone()
    conn.close()
    
    return render_template('edit_tenant.html', tenant=tenant)


# --- ROUTE 5: Add a New Tenant ---
@app.route('/add-tenant', methods=['GET', 'POST'])
@requires_auth
def add_tenant():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tenants (name, address, floor, side, base_rent, phone) VALUES (%s, %s, %s, %s, %s, %s)",
            (request.form['name'], request.form['address'], request.form['floor'], 
             request.form['side'], request.form['base_rent'], request.form['phone'])
        )
        conn.commit()
        conn.close()
        return redirect('/admin')
    return render_template('add_tenant.html')

# --- ROUTE 6: Delete a Tenant ---
@app.route('/delete-tenant/<int:id>')
@requires_auth
def delete_tenant(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # First delete their readings (Foreign Key rule), then the tenant
    cursor.execute("DELETE FROM meter_readings WHERE tenant_id = %s", (id,))
    cursor.execute("DELETE FROM tenants WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin')

# --- ROUTE 7: View Reading History (The Time Machine) ---
@app.route('/history/<int:tenant_id>')
@requires_auth
def view_history(tenant_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get Tenant Name
    cursor.execute("SELECT name FROM tenants WHERE id = %s", (tenant_id,))
    tenant = cursor.fetchone()
    
    # Get All Past Readings
    cursor.execute("SELECT * FROM meter_readings WHERE tenant_id = %s ORDER BY reading_date DESC", (tenant_id,))
    readings = cursor.fetchall()
    
    conn.close()
    return render_template('history.html', readings=readings, tenant=tenant)

# --- ROUTE 8: Edit a Specific Reading ---
@app.route('/edit-reading/<int:reading_id>', methods=['GET', 'POST'])
@requires_auth
def edit_reading(reading_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        new_reading = request.form['reading_value']
        new_date = request.form['reading_date']
        cursor.execute("UPDATE meter_readings SET reading_value=%s, reading_date=%s WHERE id=%s", 
                       (new_reading, new_date, reading_id))
        conn.commit()
        conn.close()
        return redirect('/admin') # Or redirect back to history page

    # Show current data
    cursor.execute("SELECT * FROM meter_readings WHERE id = %s", (reading_id,))
    reading = cursor.fetchone()
    conn.close()
    return render_template('edit_reading.html', reading=reading)



if __name__ == '__main__':
    app.run(debug=True)