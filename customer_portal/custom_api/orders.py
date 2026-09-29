# In your_custom_app/api/sales_order.py
import frappe
from frappe import _

@frappe.whitelist()
def get_customer_sales_orders():
    # Get the currently logged-in user
    customer_email = frappe.session.user
    
    # Fetch customer record using the logged-in user's email
    customer = frappe.get_all('Customer', filters={'custom_link_user_email': customer_email}, fields=['name'])
    
    if not customer:
        return {'message': _('No customer found for this user.')}

    customer_name = customer[0].name
    
    
      # Fetch all active quotations for the customer
    payment_made = frappe.get_all('Payment Entry', 
                                filters={'party_name': customer_name, 
                                         'status': ['!=', 'Cancelled']},  # Exclude cancelled quotations
                                fields=['name', 'posting_date', 'paid_amount', 'status','custom_amount_paid_till_date','custom_balance'])

    
    
    # Fetch sales orders for the customer
    sales_orders = frappe.get_all('Sales Order', 
                                  filters={'customer': customer_name,
                                           'status': ['!=', 'Cancelled']  # Exclude orders with status "Cancelled"
                                           }, 
                                  fields=['name', 'transaction_date', 'grand_total', 'status', 'payment_terms_template','advance_paid'])

    # Retrieve items and payment schedules for each sales order
    for order in sales_orders:
        # Fetch items for the order
        items = frappe.get_all('Sales Order Item',
                               filters={'parent': order.name},
                               fields=['item_code', 'item_name', 'qty', 'rate', 'amount'])
        order['items'] = items

        # Fetch payment schedule for the order
        payment_schedule = frappe.get_all('Payment Schedule',
                                          filters={'parent': order.name},
                                          fields=['payment_term', 'due_date', 'custom_penality_percent',
                                                  'custom_penality_amount','custom_payment_amount_penality','invoice_portion', 'payment_amount', 'paid_amount','outstanding'])
        order['payment_schedule'] = payment_schedule

    return {'sales_orders': sales_orders,"payment_made":payment_made}


@frappe.whitelist()
def get_customer_sales_invoices():
    # Get the currently logged-in user
    customer_email = frappe.session.user
    
    # Fetch customer record using the logged-in user's email
    customer = frappe.get_all('Customer', filters={'custom_link_user_email': customer_email}, fields=['name'])
    
    if not customer:
        return {'message': _('No customer found for this user.')}

    customer_name = customer[0].name

    # Fetch sales Invoice for the customer
    sales_invoice = frappe.get_all('Sales Invoice', 
                                  filters={'customer': customer_name,
                                           'status': ['!=', 'Cancelled']  # Exclude invoices with status "Cancelled"
                                           }, 
                                  fields=['name', 'posting_date', 'grand_total', 'status','outstanding_amount'])

    # Retrieve items 
    for invoice in sales_invoice:
        # Fetch items for the invoice
        items = frappe.get_all('Sales Invoice Item',
                               filters={'parent': invoice.name},
                               fields=['item_code', 'item_name', 'qty', 'rate', 'amount'])
        invoice['items'] = items

   

    return {'sales_invoice': sales_invoice}


@frappe.whitelist()
def get_customer_delivery_notes():
    # Get the currently logged-in user
    customer_email = frappe.session.user
    
    # Fetch customer record using the logged-in user's email
    customer = frappe.get_all('Customer', filters={'custom_link_user_email': customer_email}, fields=['name'])
    
    if not customer:
        return {'message': _('No customer found for this user.')}

    customer_name = customer[0].name

    # Fetch sales Invoice for the customer
    sales_invoice = frappe.get_all('Delivery Note', 
                                  filters={'customer': customer_name,
                                           'status': ['!=', 'Cancelled']  # Exclude invoices with status "Cancelled"
                                           }, 
                                  fields=['name', 'posting_date', 'grand_total', 'status'])

    # Retrieve items 
    for invoice in sales_invoice:
        # Fetch items for the invoice
        items = frappe.get_all('Delivery Note Item',
                               filters={'parent': invoice.name},
                               fields=['item_code', 'item_name', 'qty', 'rate', 'amount'])
        invoice['items'] = items

   

    return {'sales_invoice': sales_invoice}

@frappe.whitelist()
def get_customer_balance_from_gl():
    # Get the currently logged-in user
    customer_email = frappe.session.user

    # Fetch customer record using the logged-in user's email
    customer = frappe.get_all('Customer', filters={'custom_link_user_email': customer_email}, fields=['name', 'customer_name'])
    
    # Check if a customer was found for the email
    if not customer:
        return {"error": "No customer found for the logged-in user."}
    
    customer_name = customer[0].name
    customer_full_name = customer[0].customer_name
    # Abbreviate customer_name (taking first letter of each word)
    customer_abbreviation = ''.join([word[0].upper() for word in customer_full_name.split()])

    # Define the account filter
    account_filter = '11310 - Receivables - NAIRA - MACL'

    # Fetch total credits and account currency for the customer, excluding cancelled entries
    credit_result = frappe.db.sql("""
        SELECT SUM(credit), account_currency
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
        AND party = %s
        AND account = %s
        AND docstatus = 1
        AND is_cancelled = 0
        GROUP BY account_currency
    """, (customer_name, account_filter))
    
    # Extract total credit and currency
    total_credit = credit_result[0][0] if credit_result else 0
    account_currency = credit_result[0][1] if credit_result else "NGN"  # Default to "NGN" if currency is not available

    # Fetch total debits for the customer in the same currency and account, excluding cancelled entries
    total_debit = frappe.db.sql("""
        SELECT SUM(debit)
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
        AND party = %s
        AND account_currency = %s
        AND account = %s
        AND docstatus = 1
        AND is_cancelled = 0
    """, (customer_name, account_currency, account_filter))[0][0] or 0

    # Calculate available credits and balance payable
    available_credits = total_credit
    balance_payable = total_debit - total_credit

    # Return the summary as a dictionary
    return {
        "Email": customer_email,
        "Customer": customer_full_name,
        "Account Currency": account_currency,
        "Available Credits": available_credits,
        "Balance Payable": balance_payable,
        "Abr": customer_abbreviation
    }


@frappe.whitelist()
def get_last_payment():
    # Get the currently logged-in user
    customer_email = frappe.session.user

    # Fetch customer record using the logged-in user's email (assuming 'custom_link_user_email' is the correct field)
    customer = frappe.get_all('Customer', filters={'custom_link_user_email': customer_email}, fields=['name','customer_name'])
    
    if not customer:
        return {"message": "No customer record found for the logged-in user."}

    # Get the customer name from the fetched customer record
    customer_name = customer[0].get('name')

    # Query for the most recent Payment Entry for the logged-in customer
    last_payment = frappe.db.sql("""
        SELECT 
            pe.name,
            pe.posting_date,
            pe.total_allocated_amount,
            pe.unallocated_amount
        FROM
            `tabPayment Entry` pe
        WHERE
            pe.docstatus = 1  -- 1 means the document is submitted
            AND pe.party = %s  -- Filter payments for the logged-in customer
        ORDER BY
            pe.posting_date DESC
        LIMIT 1
    """, (customer_name,), as_dict=True)

    # Query for the count of payments made by the customer
    payment_count = frappe.db.sql("""
        SELECT COUNT(*) AS count
        FROM `tabPayment Entry`
        WHERE docstatus = 1
        AND party = %s
    """, (customer_name,), as_dict=True)

    if last_payment:
        # Get the related GL Entries for the last payment (optional, as per your need)
        gl_entries = frappe.db.sql("""
            SELECT
                account, debit, credit
            FROM
                `tabGL Entry`
            WHERE
                voucher_type = 'Payment Entry' 
                AND voucher_no = %s
        """, (last_payment[0].name), as_dict=True)

        # If there are GL Entries, you can process them as needed (here we just count the payments made)
        payments_made = payment_count[0].get('count')  # Get the count of all payments made

        return {
            "Total Amount": last_payment[0].total_allocated_amount,  # The total allocated amount
            "Balance Payable": last_payment[0].unallocated_amount,  # The unallocated amount
            "Paid On": last_payment[0].posting_date,  # The date of the last payment
            "Payments": payments_made  # The number of payments made so far
        }
    else:
        return {
            "message": "No payments found for the customer"
        }


import frappe
from frappe.utils import get_url

@frappe.whitelist()
def get_shared_documents():
    # Get the currently logged-in user email
    customer_email = frappe.session.user

    # Query the "File" doctype for all files that are shared and associated with the logged-in user
    files = frappe.get_all(
        'File',
        filters={'custom_user_id': customer_email},
        fields=['name', 'file_name', 'file_url', 'file_type']
    )

    # Prepare the response with file details (URL, name, and type)
    file_data = []
    for file in files:
        # Ensure to build the full URL for downloading
        file_data.append({
            "file_name": file['file_name'],
            "file_type": file['file_type'],
            "file_url": get_url(file['file_url'])  # Build the full URL for the file
        })

    # Return the file data
    return {"message": file_data}

import frappe
from frappe.utils.file_manager import save_file

@frappe.whitelist(allow_guest=True)
def upload_document():
    user = frappe.session.user
    filedata = frappe.request.files['file']
    
    if not filedata:
        return {'message': 'No file uploaded'}

    # Save the file to ERPNext using save_file method
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filedata.filename,
        "file_url": None,
        'custom_user_id':user,
        'folder':'Home/Documents Shared with Customer Portal',
        "is_private": 0,  # 0 for public, 1 for private
        "content": filedata.read()
    })
    
    file_doc.save()

    return {'message': 'Success'}

