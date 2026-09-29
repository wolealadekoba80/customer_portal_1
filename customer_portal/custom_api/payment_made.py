import frappe
from frappe import _

@frappe.whitelist()
def get_customer_payment_made():
    # Get the currently logged-in user's email
    customer_email = frappe.session.user
    
    # Fetch the customer using the logged-in user's email
    customer = frappe.get_all('Customer', 
                              filters={'custom_link_user_email': customer_email}, 
                              fields=['name'])
    
    # If no customer is found, return a message
    if not customer:
        return {'message': _('No customer found for this user.')}

    customer_name = customer[0].name

    # Fetch all active payment entries for the customer
    payments = frappe.get_all('Payment Entry', 
                               filters={'party_name': customer_name, 
                                        'status': ['!=', 'Cancelled']},  # Exclude cancelled payments
                               fields=['name', 'posting_date', 'paid_amount', 'status', 'custom_amount_paid_till_date', 'custom_balance'])

    # Fetch items attached to each payment entry
    for payment in payments:
        payment_items = frappe.get_all('Payment Entry Reference',  # Assuming 'Payment Entry Reference' links items to payments
                                        filters={'parent': payment['name']},
                                        fields=['reference_name', 'reference_doctype', 'allocated_amount'])
        
        # Fetch the actual referenced items
        for item in payment_items:
            if item['reference_doctype'] and item['reference_name']:
                # Retrieve the full document of the referenced item
                referenced_doc = frappe.get_doc(item['reference_doctype'], item['reference_name'])
                item['referenced_doc'] = referenced_doc  # Attach the full document to the item

        payment['items'] = payment_items

    return {'payments': payments}