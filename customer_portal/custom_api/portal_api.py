import os
import re
import base64
import mimetypes
from urllib.parse import unquote
import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, formatdate, add_months
from frappe.utils.pdf import get_pdf

def embed_images_as_base64(html_content):
    if not html_content:
        return html_content

    def get_base64_data_uri(raw_url):
        if not raw_url or raw_url.startswith("data:"):
            return raw_url
        clean_url = unquote(raw_url.split("?")[0].strip().strip("\"'"))
        file_path = None
        if "/private/files/" in clean_url:
            fname = clean_url.split("/private/files/", 1)[1]
            file_path = frappe.get_site_path("private", "files", fname)
        elif "/files/" in clean_url:
            fname = clean_url.split("/files/", 1)[1]
            file_path = frappe.get_site_path("public", "files", fname)
        elif clean_url.startswith("private/files/"):
            fname = clean_url.split("private/files/", 1)[1]
            file_path = frappe.get_site_path("private", "files", fname)
        elif clean_url.startswith("files/"):
            fname = clean_url.split("files/", 1)[1]
            file_path = frappe.get_site_path("public", "files", fname)

        if not file_path or not os.path.exists(file_path):
            file_record = frappe.db.get_value("File", {"file_url": raw_url}, ["file_name", "is_private"], as_dict=True)
            if file_record:
                folder = "private" if file_record.is_private else "public"
                candidate = frappe.get_site_path(folder, "files", file_record.file_name)
                if os.path.exists(candidate):
                    file_path = candidate

        if file_path and os.path.exists(file_path):
            try:
                mime_type, _ = mimetypes.guess_type(file_path)
                if not mime_type:
                    mime_type = "image/png"
                with open(file_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                return f"data:{mime_type};base64,{b64}"
            except Exception:
                pass
        return raw_url

    def replace_img(match):
        full_tag = match.group(0)
        src = match.group(1)
        data_uri = get_base64_data_uri(src)
        if data_uri != src:
            return full_tag.replace(src, data_uri)
        return full_tag

    img_pattern = re.compile(r"""<img[^>]+src=["']([^"']+)["'][^>]*>""", re.IGNORECASE)
    html_content = img_pattern.sub(replace_img, html_content)

    def replace_url(match):
        orig = match.group(0)
        url_target = match.group(1)
        data_uri = get_base64_data_uri(url_target)
        if data_uri != url_target:
            return f"url('{data_uri}')"
        return orig

    url_pattern = re.compile(r"""url\(['"]?([^'")]+)['"]?\)""", re.IGNORECASE)
    html_content = url_pattern.sub(replace_url, html_content)

    return html_content

def resolve_customer_by_email(email):
    if not email or email == "Guest":
        return None
    email = str(email).strip().lower()

    # 1. Check custom_link_user_email on Customer
    cust = frappe.db.get_value(
        "Customer",
        {"custom_link_user_email": email},
        ["name", "customer_name", "customer_group", "territory", "mobile_no", "email_id", "custom_link_user_email"],
        as_dict=True
    )
    if cust:
        return cust

    # 2. Check Contact linked to Customer via Dynamic Link
    contact_cust = frappe.db.sql("""
        SELECT dl.link_name as customer_id
        FROM `tabContact` c
        JOIN `tabDynamic Link` dl ON dl.parent = c.name AND dl.parenttype = 'Contact' AND dl.link_doctype = 'Customer'
        WHERE (LOWER(TRIM(c.email_id)) = %s OR LOWER(TRIM(c.user)) = %s)
        LIMIT 1
    """, (email, email), as_dict=True)
    if contact_cust:
        cust = frappe.db.get_value(
            "Customer",
            contact_cust[0].customer_id,
            ["name", "customer_name", "customer_group", "territory", "mobile_no", "email_id", "custom_link_user_email"],
            as_dict=True
        )
        if cust:
            return cust

    # 3. Check Portal User child table if exists
    if frappe.db.table_exists("Portal User") and frappe.db.has_column("Portal User", "user"):
        pu_cust = frappe.db.sql("""
            SELECT parent FROM `tabPortal User` WHERE LOWER(TRIM(user)) = %s AND parenttype = 'Customer' LIMIT 1
        """, (email,))
        if pu_cust:
            cust = frappe.db.get_value(
                "Customer",
                pu_cust[0][0],
                ["name", "customer_name", "customer_group", "territory", "mobile_no", "email_id", "custom_link_user_email"],
                as_dict=True
            )
            if cust:
                return cust

    # 4. Fallback matching customer email_id
    cust_by_email = frappe.db.sql("""
        SELECT name, customer_name, customer_group, territory, mobile_no, email_id, custom_link_user_email
        FROM `tabCustomer`
        WHERE LOWER(TRIM(email_id)) = %s
        LIMIT 1
    """, (email,), as_dict=True)
    if cust_by_email:
        return cust_by_email[0]

    # 5. Fallback matching customer name
    if frappe.db.exists("Customer", email):
        return frappe.db.get_value(
            "Customer",
            email,
            ["name", "customer_name", "customer_group", "territory", "mobile_no", "email_id", "custom_link_user_email"],
            as_dict=True
        )

    return None

def resolve_customer_for_user(user_email=None):
    if not user_email:
        user_email = frappe.session.user
    
    if not user_email or user_email == "Guest":
        return None

    cust = resolve_customer_by_email(user_email)
    # Auto-heal: If found but custom_link_user_email wasn't set, persist it
    if cust and not cust.get("custom_link_user_email"):
        try:
            clean_email = str(user_email).strip().lower()
            frappe.db.set_value("Customer", cust.name, "custom_link_user_email", clean_email)
            frappe.db.commit()
            cust["custom_link_user_email"] = clean_email
        except Exception:
            pass

    return cust

def is_staff_user():
    roles = frappe.get_roles(frappe.session.user)
    staff_roles = {"System Manager", "Sales Manager", "Sales User", "Accounts User", "Accounts Manager"}
    return bool(staff_roles.intersection(set(roles)))

def get_target_customer(customer_override=None):
    if is_staff_user() and customer_override:
        cust = frappe.db.get_value(
            "Customer",
            customer_override,
            ["name", "customer_name", "customer_group", "territory", "mobile_no", "email_id"],
            as_dict=True
        )
        if cust:
            return cust
    return resolve_customer_for_user()

@frappe.whitelist()
def get_portal_context(customer_override=None):
    if frappe.session.user == "Guest":
        return {"is_guest": True}

    customer = get_target_customer(customer_override)
    is_staff = is_staff_user()

    customer_list = []
    if is_staff:
        # Provide customer directory for admin preview mode
        customer_list = frappe.db.sql("""
            SELECT DISTINCT c.name, c.customer_name, c.custom_link_user_email
            FROM `tabCustomer` c
            JOIN `tabSales Order` so ON so.customer = c.name
            WHERE so.docstatus = 1
            ORDER BY c.customer_name ASC
            LIMIT 100
        """, as_dict=True)

    if not customer:
        return {
            "is_guest": False,
            "is_staff": is_staff,
            "user": frappe.session.user,
            "customer": None,
            "customer_list": customer_list,
            "message": "No customer profile linked to this user."
        }

    # Calculate Overview Metrics across customer's Sales Orders
    orders = frappe.get_all(
        "Sales Order",
        filters={"customer": customer.name, "docstatus": 1},
        fields=["name", "status", "grand_total", "total_expected_receivable", "total_collected_receivable", "current_outstanding_balance"]
    )

    total_contract_value = sum(flt(o.grand_total) for o in orders)
    total_expected = sum(flt(o.total_expected_receivable or o.grand_total) for o in orders)

    total_paid = 0.0
    total_outstanding = 0.0
    for o in orders:
        gt = flt(o.grand_total)
        if o.status == "Completed":
            c = flt(o.total_collected_receivable) if flt(o.total_collected_receivable) > 0 else gt
            total_paid += c
            total_outstanding += flt(o.current_outstanding_balance) if flt(o.current_outstanding_balance) > 0 else 0.0
        else:
            c = flt(o.total_collected_receivable)
            total_paid += c
            total_outstanding += flt(o.current_outstanding_balance if o.current_outstanding_balance is not None else max(0.0, gt - c))

    # Fallback if customer has no Sales Orders but has Sales Invoices
    if not orders:
        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"customer": customer.name, "docstatus": 1},
            fields=["grand_total", "outstanding_amount"]
        )
        if invoices:
            total_contract_value = sum(flt(inv.grand_total) for inv in invoices)
            total_expected = total_contract_value
            total_outstanding = sum(flt(inv.outstanding_amount) for inv in invoices)
            total_paid = max(0.0, total_contract_value - total_outstanding)

    percent_paid = round((total_paid / total_contract_value * 100), 1) if total_contract_value > 0 else (100.0 if total_paid > 0 else 0.0)

    # Find next upcoming milestone and any overdue milestones
    today_date = getdate(nowdate())
    milestones = frappe.db.sql("""
        SELECT rs.parent, rs.due_date, rs.expected_payment, rs.balance, rs.total_outstanding, rs.status
        FROM `tabReceivables Schedule` rs
        JOIN `tabSales Order` so ON so.name = rs.parent
        WHERE so.customer = %s AND so.docstatus = 1 AND rs.balance > 0
        ORDER BY rs.due_date ASC
    """, (customer.name,), as_dict=True)

    overdue_count = 0
    overdue_amount = 0.0
    upcoming_milestone = None

    for m in milestones:
        due_d = getdate(m.due_date)
        if due_d < today_date:
            overdue_count += 1
            overdue_amount += flt(m.balance)
        elif not upcoming_milestone:
            upcoming_milestone = {
                "order_id": m.parent,
                "due_date": str(m.due_date),
                "expected_payment": flt(m.expected_payment),
                "balance": flt(m.balance),
                "total_outstanding": flt(m.total_outstanding)
            }

    user_info = frappe.db.get_value("User", frappe.session.user, ["full_name", "user_image"], as_dict=True) or {}

    return {
        "is_guest": False,
        "is_staff": is_staff,
        "user": {
            "email": frappe.session.user,
            "full_name": user_info.get("full_name") or customer.customer_name,
            "user_image": user_info.get("user_image")
        },
        "customer": customer,
        "customer_list": customer_list,
        "metrics": {
            "total_orders": len(orders),
            "total_contract_value": total_contract_value,
            "total_expected": total_expected,
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            "percent_paid": percent_paid,
            "overdue_count": overdue_count,
            "overdue_amount": overdue_amount,
            "upcoming_milestone": upcoming_milestone
        }
    }

@frappe.whitelist()
def get_customer_orders(customer_override=None):
    customer = get_target_customer(customer_override)
    if not customer:
        return {"orders": []}

    orders = frappe.get_all(
        "Sales Order",
        filters={"customer": customer.name, "docstatus": ["!=", 2]},
        fields=[
            "name", "transaction_date", "delivery_date", "status", "grand_total",
            "currency", "company", "project", "total_expected_receivable",
            "total_collected_receivable", "current_outstanding_balance",
            "custom_penality_rate"
        ],
        order_by="transaction_date desc"
    )

    enriched_orders = []
    today_date = getdate(nowdate())

    for o in orders:
        # Items
        items = frappe.get_all(
            "Sales Order Item",
            filters={"parent": o.name},
            fields=["item_code", "item_name", "description", "qty", "rate", "amount"]
        )

        # Receivables Schedule
        schedule_rows = frappe.get_all(
            "Receivables Schedule",
            filters={"parent": o.name},
            fields=[
                "idx", "due_date", "expected_payment", "amount_paid",
                "previous_balance", "balance", "total_outstanding", "status",
                "penalty_rate", "penalty_amount", "total_due_with_penalty"
            ],
            order_by="idx asc"
        )

        # Progress
        gt = flt(o.grand_total)
        if o.status == "Completed":
            collected = flt(o.total_collected_receivable) if flt(o.total_collected_receivable) > 0 else gt
            outstanding = flt(o.current_outstanding_balance) if flt(o.current_outstanding_balance) > 0 else 0.0
            percent = 100.0
        else:
            collected = flt(o.total_collected_receivable)
            outstanding = flt(o.current_outstanding_balance if o.current_outstanding_balance is not None else max(0.0, gt - collected))
            percent = round((collected / gt * 100), 1) if gt > 0 else 0.0

        enriched_orders.append({
            "name": o.name,
            "transaction_date": str(o.transaction_date) if o.transaction_date else "",
            "delivery_date": str(o.delivery_date) if o.delivery_date else "",
            "status": o.status,
            "grand_total": gt,
            "currency": o.currency or "NGN",
            "company": o.company,
            "project": o.project or "",
            "total_expected": flt(o.total_expected_receivable or gt),
            "total_collected": collected,
            "current_outstanding": outstanding,
            "penalty_rate": flt(o.custom_penality_rate),
            "percent_paid": percent,
            "items": items,
            "receivables_schedule": schedule_rows
        })

    return {"orders": enriched_orders}

@frappe.whitelist()
def get_customer_payments(customer_override=None):
    customer = get_target_customer(customer_override)
    if not customer:
        return {"payments": []}

    payments = frappe.db.sql("""
        SELECT 
            pe.name, pe.posting_date, pe.paid_amount, pe.mode_of_payment, 
            pe.reference_no, pe.reference_date, pe.status, pe.remarks,
            per.reference_doctype, per.reference_name, per.allocated_amount
        FROM `tabPayment Entry` pe
        LEFT JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        WHERE pe.party_type = 'Customer' AND pe.party = %s AND pe.docstatus = 1
        ORDER BY pe.posting_date DESC, pe.creation DESC
    """, (customer.name,), as_dict=True)

    # Group references by payment entry
    grouped = {}
    for p in payments:
        p_name = p.name
        if p_name not in grouped:
            grouped[p_name] = {
                "name": p.name,
                "posting_date": str(p.posting_date) if p.posting_date else "",
                "paid_amount": flt(p.paid_amount),
                "mode_of_payment": p.mode_of_payment or "Bank Transfer",
                "reference_no": p.reference_no or "",
                "status": p.status,
                "remarks": p.remarks or "",
                "references": []
            }
        if p.reference_name:
            grouped[p_name]["references"].append({
                "doctype": p.reference_doctype,
                "name": p.reference_name,
                "allocated_amount": flt(p.allocated_amount)
            })

    return {"payments": list(grouped.values())}

@frappe.whitelist()
def get_customer_invoices(customer_override=None):
    customer = get_target_customer(customer_override)
    if not customer:
        return {"invoices": []}

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"customer": customer.name, "docstatus": 1},
        fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "status", "currency", "company"],
        order_by="posting_date desc"
    )

    enriched = []
    for inv in invoices:
        items = frappe.get_all("Sales Invoice Item", filters={"parent": inv.name}, fields=["item_name", "qty", "rate", "amount"])
        inv["items"] = items
        inv["posting_date"] = str(inv.posting_date) if inv.posting_date else ""
        inv["due_date"] = str(inv.due_date) if inv.due_date else ""
        enriched.append(inv)

    return {"invoices": enriched}

@frappe.whitelist()
def get_customer_statement(from_date=None, to_date=None, customer_override=None):
    customer = get_target_customer(customer_override)
    if not customer:
        return {"statement": []}

    if not from_date:
        # Auto-detect earliest transaction date so historical records are not excluded
        earliest_date = frappe.db.sql("""
            SELECT MIN(posting_date)
            FROM `tabGL Entry`
            WHERE party_type = 'Customer' AND party = %s AND docstatus = 1 AND is_cancelled = 0
        """, (customer.name,))[0][0]
        if earliest_date:
            from_date = str(earliest_date)
        else:
            from_date = f"{getdate(nowdate()).year}-01-01"
    if not to_date:
        to_date = nowdate()

    # 1. Opening Balance Brought Forward
    opening_bal = frappe.db.sql("""
        SELECT SUM(debit - credit) as balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer' AND party = %s AND posting_date < %s AND docstatus = 1 AND is_cancelled = 0
    """, (customer.name, from_date))[0][0] or 0.0

    # 2. Ledger Entries in period
    entries = frappe.db.sql("""
        SELECT 
            posting_date, voucher_type, voucher_no, debit, credit, remarks
        FROM `tabGL Entry`
        WHERE party_type = 'Customer' AND party = %s 
          AND posting_date BETWEEN %s AND %s
          AND docstatus = 1 AND is_cancelled = 0
        ORDER BY posting_date ASC, creation ASC
    """, (customer.name, from_date, to_date), as_dict=True)

    running_bal = flt(opening_bal)
    statement_rows = []
    total_debit = 0.0
    total_credit = 0.0

    for e in entries:
        d = flt(e.debit)
        c = flt(e.credit)
        total_debit += d
        total_credit += c
        running_bal += (d - c)
        statement_rows.append({
            "posting_date": str(e.posting_date),
            "voucher_type": e.voucher_type,
            "voucher_no": e.voucher_no,
            "debit": d,
            "credit": c,
            "balance": round(running_bal, 2),
            "remarks": e.remarks or ""
        })

    return {
        "customer": customer,
        "from_date": from_date,
        "to_date": to_date,
        "opening_balance": round(flt(opening_bal), 2),
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "closing_balance": round(running_bal, 2),
        "entries": statement_rows
    }

@frappe.whitelist()
def get_customer_deliveries(customer_override=None):
    customer = get_target_customer(customer_override)
    if not customer:
        return {"deliveries": []}

    notes = frappe.get_all(
        "Delivery Note",
        filters={"customer": customer.name, "docstatus": 1},
        fields=["name", "posting_date", "status", "grand_total", "company"],
        order_by="posting_date desc"
    )
    for n in notes:
        n["items"] = frappe.get_all("Delivery Note Item", filters={"parent": n.name}, fields=["item_name", "qty"])
        n["posting_date"] = str(n.posting_date) if n.posting_date else ""

    return {"deliveries": notes}

@frappe.whitelist()
def get_shared_documents(customer_override=None):
    customer = get_target_customer(customer_override)
    if not customer:
        return {"documents": []}

    # Documents attached to Customer or Sales Orders - ONLY PUBLIC FILES
    so_names = frappe.get_all("Sales Order", filters={"customer": customer.name}, pluck="name")
    target_names = [customer.name] + so_names

    files = frappe.get_all(
        "File",
        filters={"attached_to_name": ["in", target_names], "is_private": 0},
        fields=["name", "file_name", "file_url", "file_size", "creation", "is_private"],
        order_by="creation desc"
    )

    return {"documents": files}

@frappe.whitelist()
def upload_customer_document():
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required to upload documents."))

    customer = resolve_customer_for_user()
    if not customer:
        frappe.throw(_("No customer profile found for user."))

    if "file" not in frappe.request.files:
        frappe.throw(_("No file provided."))

    uploaded = frappe.request.files["file"]
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": uploaded.filename,
        "attached_to_doctype": "Customer",
        "attached_to_name": customer.name,
        "is_private": 0,
        "content": uploaded.read()
    })
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "file_name": file_doc.file_name, "file_url": file_doc.file_url}

@frappe.whitelist(allow_guest=True)
def send_support_message(subject=None, message=None, sender_email=None, sender_name=None, issue_type=None, priority="Medium", sender_phone=None, attachment=None):
    from metro_custom_app.custom_api.it_support import create_portal_ticket
    return create_portal_ticket(
        subject=subject,
        message=message,
        issue_type=issue_type,
        priority=priority,
        sender_email=sender_email,
        sender_name=sender_name,
        sender_phone=sender_phone,
        attachment=attachment
    )

@frappe.whitelist()
def get_customer_tickets():
    from metro_custom_app.custom_api.it_support import get_customer_tickets as _get_tickets
    return _get_tickets()

@frappe.whitelist()
def get_portal_ticket_conversation(ticket_id=None):
    if not ticket_id:
        ticket_id = frappe.form_dict.get("ticket_id")
    from metro_custom_app.custom_api.it_support import get_ticket_thread
    return get_ticket_thread(ticket_id)

@frappe.whitelist()
def reply_portal_ticket(ticket_id=None, message=None):
    if not ticket_id:
        ticket_id = frappe.form_dict.get("ticket_id")
    if not message:
        message = frappe.form_dict.get("message")
    from metro_custom_app.custom_api.it_support import post_ticket_reply
    return post_ticket_reply(ticket_id=ticket_id, message=message, is_customer=True)

@frappe.whitelist(allow_guest=True)
def portal_login(usr=None, pwd=None):
    if not usr:
        usr = frappe.form_dict.get("usr")
    if not pwd:
        pwd = frappe.form_dict.get("pwd")

    if not usr or not pwd:
        return {"status": "error", "message": _("Please enter both email address and password.")}

    usr = str(usr).strip().lower()

    # 1. Check if User exists in tabUser
    user_exists = frappe.db.exists("User", usr)
    if not user_exists:
        # Check if they exist as a registered Customer in ERPNext
        cust = resolve_customer_by_email(usr)
        if cust:
            return {
                "status": "needs_activation",
                "message": _("Welcome! We found your customer record for {0}, but your portal login has not been activated yet. Click 'Set / Activate Password' to receive your secure setup link.").format(cust.customer_name or cust.name),
                "customer_name": cust.customer_name,
                "email": usr
            }
        return {
            "status": "error",
            "message": _("No account found with this email. Please check your spelling or contact AMGL support.")
        }

    # 2. Check if user is enabled
    enabled = frappe.db.get_value("User", usr, "enabled")
    if not enabled:
        return {
            "status": "error",
            "message": _("This account is currently inactive. Please contact support at it@metroandcastle.com.")
        }

    # 3. Authenticate with Frappe LoginManager
    try:
        frappe.local.form_dict["usr"] = usr
        frappe.local.form_dict["pwd"] = pwd
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.AuthenticationError:
        frappe.clear_messages()
        return {
            "status": "error",
            "message": _("Incorrect password. Please verify your credentials or click 'Forgot Password' below.")
        }
    except Exception as e:
        frappe.clear_messages()
        return {
            "status": "error",
            "message": str(e) or _("Authentication error. Please try again.")
        }

    # 4. Resolve Customer and auto-link
    cust = resolve_customer_for_user(usr)

    return {
        "status": "success",
        "message": _("Logged In"),
        "user": usr,
        "customer_name": cust.customer_name if cust else None,
        "is_staff": is_staff_user()
    }

@frappe.whitelist(allow_guest=True)
def portal_reset_password(email=None):
    if not email:
        email = frappe.form_dict.get("email")

    if not email:
        return {"status": "error", "message": _("Please enter a valid email address.")}

    email = str(email).strip().lower()

    # Case 1: User already exists
    if frappe.db.exists("User", email):
        user_doc = frappe.get_doc("User", email)
        if not user_doc.enabled:
            return {"status": "error", "message": _("This account is disabled. Please contact customer support.")}
        try:
            user_doc.reset_password(send_email=True)
            return {
                "status": "success",
                "message": _("A password reset link has been sent to {0}. Please check your inbox.").format(email)
            }
        except Exception as e:
            return {"status": "error", "message": _("Failed to send reset link: ") + str(e)}

    # Case 2: User does not exist, but Customer is registered in ERPNext
    cust = resolve_customer_by_email(email)
    if cust:
        try:
            new_user = frappe.new_doc("User")
            new_user.email = email
            new_user.first_name = cust.customer_name or "Customer"
            new_user.user_type = "Website User"
            new_user.send_welcome_email = 0
            new_user.append("roles", {"role": "Customer"})
            new_user.insert(ignore_permissions=True)

            frappe.db.set_value("Customer", cust.name, "custom_link_user_email", email)
            new_user.reset_password(send_email=True)
            frappe.db.commit()

            return {
                "status": "success",
                "message": _("Account activated! A password setup link has been sent to {0}. Open the link to set your password and access your customer portal.").format(email)
            }
        except Exception as e:
            return {"status": "error", "message": _("Error activating account: ") + str(e)}

    # Case 3: Email not found
    return {
        "status": "not_found",
        "message": _("This email is not registered in our records. Please contact support at it@metroandcastle.com.")
    }

def render_statement_pdf_html(stmt, customer):
    cust_name = customer.get("customer_name") or customer.get("name")
    cust_id = customer.get("name")
    email = customer.get("email_id") or ""
    mobile = customer.get("mobile_no") or ""

    rows_html = []
    if not stmt.get("entries"):
        rows_html.append('<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 16px;">No ledger transactions recorded in this period.</td></tr>')
    else:
        for e in stmt.get("entries", []):
            d_val = flt(e.get("debit", 0))
            c_val = flt(e.get("credit", 0))
            d_str = f"₦{d_val:,.2f}" if d_val > 0 else "&mdash;"
            c_str = f"₦{c_val:,.2f}" if c_val > 0 else "&mdash;"
            bal_str = f"₦{flt(e.get('balance', 0)):,.2f}"
            rows_html.append(f"""
            <tr>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; white-space: nowrap;">{e.get('posting_date')}</td>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0;">{e.get('voucher_type')}</td>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-family: monospace;">{e.get('voucher_no')}</td>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">{d_str}</td>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #10b981;">{c_str}</td>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: bold;">{bal_str}</td>
              <td style="padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-size: 9px; color: #64748b;">{e.get('remarks') or ''}</td>
            </tr>
            """)

    table_content = "\n".join(rows_html)
    op_bal = f"₦{flt(stmt.get('opening_balance', 0)):,.2f}"
    tot_deb = f"₦{flt(stmt.get('total_debit', 0)):,.2f}"
    tot_cred = f"₦{flt(stmt.get('total_credit', 0)):,.2f}"
    cl_bal = f"₦{flt(stmt.get('closing_balance', 0)):,.2f}"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Statement of Account - AMGL</title>
      <style>
        body {{
          font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
          font-size: 11px;
          color: #1e293b;
          margin: 20px;
        }}
        .header-table {{
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 20px;
          border-bottom: 2px solid #3e4095;
          padding-bottom: 12px;
        }}
        .company-title {{
          font-size: 20px;
          font-weight: bold;
          color: #3e4095;
          letter-spacing: -0.01em;
        }}
        .company-subtitle {{
          color: #64748b;
          font-size: 11px;
          margin-top: 2px;
        }}
        .doc-title {{
          font-size: 16px;
          font-weight: bold;
          color: #0f172a;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }}
        .meta-box {{
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 6px;
          padding: 12px;
          margin-bottom: 18px;
        }}
        .summary-table {{
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 18px;
        }}
        .summary-table td {{
          padding: 10px 8px;
          border: 1px solid #cbd5e1;
          text-align: center;
          background: #ffffff;
        }}
        .summary-lbl {{
          font-size: 9px;
          color: #64748b;
          text-transform: uppercase;
          font-weight: 600;
          margin-bottom: 4px;
        }}
        .summary-val {{
          font-size: 13px;
          font-weight: bold;
          color: #0f172a;
        }}
        .txn-table {{
          width: 100%;
          border-collapse: collapse;
          font-size: 10px;
        }}
        .txn-table th {{
          background: #3e4095;
          color: #ffffff;
          padding: 8px 6px;
          text-align: left;
          font-weight: 600;
          font-size: 9.5px;
          text-transform: uppercase;
        }}
        .txn-table tr:nth-child(even) {{
          background: #f8fafc;
        }}
        .footer {{
          margin-top: 30px;
          font-size: 9px;
          color: #64748b;
          text-align: center;
          border-top: 1px solid #e2e8f0;
          padding-top: 12px;
          line-height: 1.5;
        }}
      </style>
    </head>
    <body>
      <table class="header-table">
        <tr>
          <td style="vertical-align: top; width: 60%;">
            <div class="company-title">ABDUL-METRO GROUP LIMITED</div>
            <div class="company-subtitle">AMGL Corporate Customer Portal</div>
            <div style="color: #64748b; font-size: 10px; margin-top: 3px;">Website: https://abdulmetrogroup.com</div>
          </td>
          <td style="vertical-align: top; width: 40%; text-align: right;">
            <div class="doc-title">Statement of Account</div>
            <div style="font-size: 10.5px; color: #475569; margin-top: 4px;">Period: <strong>{stmt.get('from_date')}</strong> to <strong>{stmt.get('to_date')}</strong></div>
            <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Generated on {nowdate()}</div>
          </td>
        </tr>
      </table>

      <div class="meta-box">
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="width: 60%; vertical-align: top;">
              <div style="font-size: 9px; color: #64748b; text-transform: uppercase; font-weight: 600;">Customer Details</div>
              <div style="font-size: 14px; font-weight: bold; color: #0f172a; margin-top: 2px;">{cust_name}</div>
              <div style="font-size: 10px; color: #64748b; margin-top: 3px;">{email} {('• ' + mobile) if mobile else ''}</div>
            </td>
            <td style="width: 40%; vertical-align: top; text-align: right;">
              <div style="font-size: 9px; color: #64748b; text-transform: uppercase; font-weight: 600;">Account Number / Code</div>
              <div style="font-size: 13px; font-weight: bold; font-family: monospace; color: #3e4095; margin-top: 2px;">{cust_id}</div>
              <div style="font-size: 10px; color: #10b981; font-weight: 600; margin-top: 3px;">Verified Customer</div>
            </td>
          </tr>
        </table>
      </div>

      <table class="summary-table">
        <tr>
          <td>
            <div class="summary-lbl">Opening Balance</div>
            <div class="summary-val">{op_bal}</div>
          </td>
          <td>
            <div class="summary-lbl">Total Invoiced (Debits)</div>
            <div class="summary-val">{tot_deb}</div>
          </td>
          <td>
            <div class="summary-lbl">Total Paid (Credits)</div>
            <div class="summary-val" style="color: #10b981;">{tot_cred}</div>
          </td>
          <td>
            <div class="summary-lbl">Closing Outstanding</div>
            <div class="summary-val" style="color: #ed3237;">{cl_bal}</div>
          </td>
        </tr>
      </table>

      <table class="txn-table">
        <thead>
          <tr>
            <th style="width: 12%;">Date</th>
            <th style="width: 16%;">Voucher Type</th>
            <th style="width: 18%;">Voucher #</th>
            <th style="width: 14%; text-align: right;">Debit (₦)</th>
            <th style="width: 14%; text-align: right;">Credit (₦)</th>
            <th style="width: 14%; text-align: right;">Balance (₦)</th>
            <th style="width: 12%;">Remarks</th>
          </tr>
        </thead>
        <tbody>
          {table_content}
        </tbody>
      </table>

      <div class="footer">
        This is an official computer-generated statement issued by Abdul-Metro Group Limited (AMGL) Portal.<br>
        For inquiries or reconciliation, please contact it@metroandcastle.com or visit https://abdulmetrogroup.com.
      </div>
    </body>
    </html>
    """

@frappe.whitelist()
def download_payment_receipt(payment_name=None):
    if not payment_name:
        payment_name = frappe.form_dict.get("payment_name")
    if not payment_name:
        frappe.throw(_("Payment name is required."))

    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required."))

    customer = get_target_customer()
    pe = frappe.db.get_value("Payment Entry", payment_name, ["name", "party_type", "party", "docstatus"], as_dict=True)
    if not pe or pe.docstatus != 1:
        frappe.throw(_("Submitted Payment Entry not found."))

    if not is_staff_user():
        if not customer or pe.party_type != "Customer" or pe.party != customer.name:
            frappe.throw(_("You are not authorized to view this receipt."))

    frappe.flags.ignore_print_permissions = True
    frappe.flags.ignore_permissions = True
    try:
        try:
            html = frappe.get_print("Payment Entry", payment_name, print_format="Payment Receipt For Metro", as_pdf=False)
        except Exception:
            html = frappe.get_print("Payment Entry", payment_name, as_pdf=False)

        html = embed_images_as_base64(html)
        pdf_data = get_pdf(html)
    finally:
        frappe.flags.ignore_print_permissions = False
        frappe.flags.ignore_permissions = False

    frappe.response.filename = f"Receipt-{payment_name}.pdf"
    frappe.response.filecontent = pdf_data
    frappe.response.type = "download"

@frappe.whitelist()
def download_customer_statement_pdf(from_date=None, to_date=None, customer_override=None):
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required."))

    customer = get_target_customer(customer_override)
    if not customer:
        frappe.throw(_("Customer profile not found."))

    stmt = get_customer_statement(from_date=from_date, to_date=to_date, customer_override=customer.name if is_staff_user() else None)
    html = render_statement_pdf_html(stmt, customer)
    html = embed_images_as_base64(html)
    pdf_data = get_pdf(html)

    safe_name = "".join(c for c in (customer.customer_name or customer.name) if c.isalnum() or c in "-_")
    frappe.response.filename = f"AMGL_Statement_{safe_name}_{stmt['from_date']}_to_{stmt['to_date']}.pdf"
    frappe.response.filecontent = pdf_data
    frappe.response.type = "download"
