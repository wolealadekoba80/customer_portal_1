import frappe

def get_context(context):
    context.no_cache = 1
    context.title = "AMGL | Customer Portal"
    context.brand_logo = "/files/Metro New Logo Design.png"
    context.company_logo = "/files/Metro New Logo Design.png"
    user = frappe.session.user
    context.user = user
    context.is_guest = (user == "Guest")
    if not context.is_guest:
        context.user_full_name = frappe.utils.get_fullname(user)
        try:
            from customer_portal.custom_api.portal_api import is_staff_user, resolve_customer_for_user
            context.is_staff = is_staff_user()
            context.customer = resolve_customer_for_user(user)
        except Exception:
            context.is_staff = False
            context.customer = None
    else:
        context.user_full_name = "Guest"
        context.is_staff = False
        context.customer = None
    return context
