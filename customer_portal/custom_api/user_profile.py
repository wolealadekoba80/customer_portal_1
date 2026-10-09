import frappe
from frappe.utils import get_url
import frappe

@frappe.whitelist()
def get_customer_profile():
    # Get the currently logged-in user email
    customer_email = frappe.session.user

    # Query the Customer Profile for the logged-in user
    profile = frappe.get_all(
        'Customer Profile',
        filters={'user_id': customer_email},
        fields=['*']
    )

    # Return the profile data
    return profile

import frappe
from frappe.utils.file_manager import save_file
import os


@frappe.whitelist()
def update_customer_profile(first_name=None, last_name=None, phone=None, address=None, city=None, state=None, profile_image=None):
    # Get the currently logged-in user email
    customer_email = frappe.session.user

    # Find the customer profile for the logged-in user
    profile = frappe.get_all(
        'Customer Profile',
        filters={'user_id': customer_email},
        fields=['name', 'image']  # Fetch current image as well
    )

    if not profile:
        return {"status": "error", "message": "Customer profile not found"}

    profile_name = profile[0]['name']
    profile_images = frappe.request.files.get('profile_image')
    
    # Handle profile image upload only if a new image is provided
    if profile_images:
        try:
            # Retrieve the uploaded image from the form data
            profile_image = frappe.request.files.get('profile_image')

            if not profile_image:
                return {'status': 'error', 'message': 'No file uploaded'}

            # Save the file to ERPNext using save_file method (this automatically stores it in the File Manager)
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": profile_image.filename,
                "is_private": 0,  # 0 for public, 1 for private
                "content": profile_image.read(),  # Read file content
                "attached_to_doctype": "Customer Profile",
                "attached_to_name": profile_name,
                "folder": "Home"  # You can change this to any folder you prefer
            })
    
            # Save the file
            file_doc.save()

            # Get the file URL after saving
            image_url = file_doc.file_url

            # Update the Customer Profile with the new image URL
            frappe.db.set_value('Customer Profile', profile_name, 'image', image_url)

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Failed to upload profile image")
            return {"status": "error", "message": f"Failed to upload image: {e}"}

    # Update other profile fields only if they are provided (not None)
    try:
        if first_name is not None:
            frappe.db.set_value('Customer Profile', profile_name, 'first_name', first_name)
        if last_name is not None:
            frappe.db.set_value('Customer Profile', profile_name, 'last_name', last_name)
        if phone is not None:
            frappe.db.set_value('Customer Profile', profile_name, 'phone', phone)
        if address is not None:
            frappe.db.set_value('Customer Profile', profile_name, 'street_1_ba', address)
        if city is not None:
            frappe.db.set_value('Customer Profile', profile_name, 'city_ba', city)
        if state is not None:
            frappe.db.set_value('Customer Profile', profile_name, 'state_ba', state)

        # Commit the transaction to save changes
        frappe.db.commit()

        return {"status": "success", "message": "Profile updated successfully"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to update customer profile")
        return {"status": "error", "message": f"Failed to update profile: {e}"}
