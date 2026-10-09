import frappe
from frappe import throw, msgprint, _

@frappe.whitelist()
def get_keys():
    user = frappe.get_doc('User', frappe.session.user)

    # Generate a new API secret key for the user
    new_api_secret = user.custom_secret

    frappe.response["message"] = {
        "sid": frappe.session.sid,
        "user": user.name,
        "api_key": user.api_key,
        "api_secret": new_api_secret
    }
    return

import frappe
from frappe import _

@frappe.whitelist()
def generate_keys():
    """
    Generate API key and API secret for the currently logged-in user.

    :return: dict - A response dictionary containing the generated keys or an error message.
    """
    
    # Get the current user from the session
    user = frappe.session.user

    # Check if the user exists
    if not frappe.get_value("User", user):
        return {"message": _("User not found"), "status": "error"}

    try:
        # Fetch user details
        user_details = frappe.get_doc("User", user)

        # Generate API secret
        api_secret = frappe.generate_hash(length=15)

        # If API key is not set, generate API key
        if not user_details.api_key:
            api_key = frappe.generate_hash(length=15)
            user_details.api_key = api_key
        else:
            api_key = user_details.api_key  # Use existing API key if it already exists

        # Set the new API secret and any custom secret if needed
        user_details.api_secret = api_secret
        user_details.custom_secret = api_secret  # Set custom_secret field

        # Save user details
        user_details.save()

        # Optionally, commit the transaction (usually handled by Frappe)
        frappe.db.commit()

        return {
            "api_key": user_details.api_key,
            "api_secret": user_details.custom_secret,
            "message": _("API keys generated successfully."),
            "status": "success"
        }

    except Exception as e:
        # Log the error and return a message
        frappe.log_error(frappe.get_traceback(), "API Key Generation Error")
        return {
            "message": _("An error occurred: ") + str(e),
            "status": "error"
        }

import frappe

def force_session_refresh_without_logout(user):
    """Regenerate CSRF token without logging the user out."""
    # Ensure the user is authenticated
    if frappe.session.user == user and user != "Guest":
        # Generate and return a new CSRF token without logout
        return frappe.sessions.get_csrf_token()
    else:
        raise frappe.PermissionError("User is not logged in or session is invalid.")

@frappe.whitelist(allow_guest=True)
def regenerate_session():
    """Custom endpoint to regenerate the session and provide a new CSRF token."""
    user = frappe.session.user
    if user == "Guest":
        return {"error": "Not logged in"}
    
    # Regenerate the CSRF token
    try:
        csrf_token = force_session_refresh_without_logout(user)
        return {"csrf_token": csrf_token}
    except frappe.PermissionError as e:
        return {"error": str(e)}

import frappe
from frappe import throw, msgprint, _

@frappe.whitelist(allow_guest=True)
def login(usr, pwd):
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.exceptions.AuthenticationError:
        frappe.clear_messages()
        frappe.local.response["message"] = {
            "success_key": 0,
            "message": "Authentication Failed"
        }
        return

    user = frappe.get_doc('User', frappe.session.user)

    # Generate a new API secret key for the user
    new_api_secret = user.custom_secret

    frappe.response["message"] = {
        "sid": frappe.session.sid,
        "user": user.name,
        "api_key": user.api_key,
        "api_secret": new_api_secret
    }
    return

# signup.py
import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def sign_up(first_name, email, password):
    # Check if the email is already registered
    if frappe.db.exists("User", email):
        frappe.throw(_("Email already exists."))

    # Create a new user
    user = frappe.new_doc("User")
    user.first_name = first_name
    user.email = email
    user.username = email  # Use email as the username
    user.new_password = password  # Set the user's password
    user.role_profile_name = "portal"  # Set the user's role_profile_name
    user.enabled = 1  # Enable the user

    try:
        # Insert the new user, ignoring permissions
        user.insert(ignore_permissions=True)
        
        # Set the full name for the customer creation
        full_name = f"{first_name} {user.last_name or ''}".strip()
        
        # Check if a Customer linked to this user email already exists
        if not frappe.db.exists("Customer", {"custom_link_user_email": email}):
            # Create a new Customer document
            new_customer = frappe.get_doc({
                'doctype': 'Customer',
                'customer_name': full_name,  # Set the full name as customer name
                'customer_group': 'All Customer Groups',  # Specify a valid customer group
                'territory': 'All Territories',  # Specify a valid territory
                'custom_link_user_email': email  # Link the customer to the user email
            })
            
            new_customer.insert(ignore_permissions=True)  # Insert the customer document

        # Commit changes to the database
        frappe.db.commit()
        
    except frappe.PermissionError:
        frappe.throw(_("Insufficient permissions to create user."))

    # Optionally, send a welcome email to the user
    frappe.sendmail(
        recipients=[email],
        subject=_("Welcome to ERPNext!"),
        message=_("Thank you for signing up, {}! You can now log in using your email and password.").format(first_name)
    )

    return {
        "message": _("User created successfully.")
    }
