// Check if the user is logged in and toggle login/logout links accordingly
function checkLoginStatus() {
    fetch('/api/method/frappe.auth.get_logged_user', {
        method: 'GET',
        credentials: 'include' // Important for sending cookies with the request
    })
        .then(response => response.json())
        .then(data => {
            const loginLink = document.getElementById("login-link");
            const logoutLink = document.getElementById("logout-link");

            if (data.message) {
                // User is logged in
                loginLink.style.display = "none";
                logoutLink.style.display = "block";
            } else {
                // User is not logged in
                loginLink.style.display = "block";
                logoutLink.style.display = "none";
            }
        })
        .catch(error => {
            console.error("Error checking login status:", error);
            // Default to logged-out view if there’s an error
            document.getElementById("login-link").style.display = "block";
            document.getElementById("logout-link").style.display = "none";
        });
}

// Log the user out
function logoutUser() {
    fetch('/api/method/logout', {
        method: 'GET',
        credentials: 'include'
    })
        .then(() => {
            window.location.href = "/client_portal/access_portal/login"; // Redirect to login page after logout
        })
        .catch(error => console.error("Error logging out:", error));
}

// Call the checkLoginStatus function on page load
document.addEventListener("DOMContentLoaded", checkLoginStatus);

async function fetchOrders() {
    try {
        const response = await fetch('/api/method/customer_portal.custom_api.orders.get_customer_sales_orders');
        const result = await response.json();

        const salesOrders = result.message && result.message.sales_orders;
        const payments = result.message && result.message.payment_made;
        // console.log(result);

        if (salesOrders) {
            const orderItemsContainer = document.getElementById('order-items');
            // Initialize the total amount and total advance paid
            let totalAmount = 0;

            salesOrders.forEach(order => {
                // Assuming there's only one item per order as per your example
                order.items.forEach(item => {
                    // console.log(item);
                    // Add the item amount to the total amount
                    totalAmount += item.amount;

                    // Create row for each sales order
                    const orderRow = document.createElement('tr');
                    orderRow.innerHTML = `
                        <td>${item.item_code}</td> <!-- Display item code here -->
                        <td>${order.name}</td>
                        <td>${order.transaction_date}</td>
                        <td>${order.status}</td>
                        <td>₦${item.amount.toLocaleString()}</td>
                        <td><button onclick="togglePaymentSchedule('${order.name}')">View Schedule</button></td>
                    `;
                    orderItemsContainer.appendChild(orderRow);
                });

                // Add a table row for the payment schedule, initially hidden
                const scheduleRow = document.createElement('tr');
                scheduleRow.id = `schedule-${order.name}`;
                scheduleRow.style.display = 'none';
                scheduleRow.innerHTML = `
                    <td colspan="6">
                        <div>
                            <h4>Payment Schedule</h4>
                            <table class="cart-table">
                                <thead>
                                    <tr>
                                        <th>Payment Term</th>
                                        <th>Due Date</th>
                                        <th>Invoice Portion (%)</th>
                                        <th>Payment Amount</th>
                                        <th>Penalty Amount</th>
                                        <th>Payment Amount + Penalty</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${order.payment_schedule.map(schedule => `
                                        <tr>
                                            <td>${schedule.payment_term}</td>
                                            <td>${schedule.due_date}</td>
                                            <td>${schedule.invoice_portion}</td>
                                            <td>₦${schedule.payment_amount.toLocaleString()}</td>
                                            <td>₦${schedule.custom_penality_amount.toLocaleString()}</td>
                                            <td>₦${schedule.custom_payment_amount_penality.toLocaleString()}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </td>
                `;
                orderItemsContainer.appendChild(scheduleRow);


            });

            // Calculate total advance paid using reduce on salesOrders
            let grandPaid = salesOrders.reduce((acc, order) => acc + order.grand_total, 0);
            let advancePaid = payments.reduce((acc, amount) => acc + amount.paid_amount, 0);
            let balance12 = grandPaid - advancePaid
            // Calculate the balance as total amount - total advance paid
           
            // After all orders are processed, add the total amount row
            const totalRow = document.createElement('tr');
            totalRow.innerHTML = `
                <td colspan="4" style="text-align:right;"><strong>Total Amount</strong></td>
                <td colspan="2">
                    <span id="total-amount">₦${totalAmount.toLocaleString()}</span>
                </td>
                
            `;
            orderItemsContainer.appendChild(totalRow);

            // Initialize total payment penalty amount
            let totalPaymentPenaltyAmount = 0;
            let totalPenaltyAmount = 0;

            // Loop through orders to calculate total payment penalty amount
            salesOrders.forEach(order => {
                order.payment_schedule.forEach(schedule => {
                    totalPaymentPenaltyAmount += schedule.paid_amount || 0;
                    totalPenaltyAmount += schedule.custom_penality_amount || 0;
                });
            });

            let pap = totalPenaltyAmount + grandPaid
            let balance =  balance12;

            // Add the row for Total Payment Amount + Penalty
            const paymentAmountPenalityRow = document.createElement('tr');
            paymentAmountPenalityRow.innerHTML = `
                <td colspan="4" style="text-align:right;"><strong>Total Payment Amount + Penalty</strong></td>
                <td colspan="2">
                <span id="total-payment-penalty">₦${pap.toLocaleString()}</span>
                </td>
            `;
            orderItemsContainer.appendChild(paymentAmountPenalityRow);
            // Create the row for the total advance paid, below the total amount
            const advancePaidRow = document.createElement('tr');
            advancePaidRow.innerHTML = `
            <td colspan="4" style="text-align:right;"><strong>Total Advance Paid</strong></td>
            <td colspan="2">
            <span id="total-advance-paid">₦${advancePaid.toLocaleString()}</span>
            </td>
            `;

            // Add the advance paid row below the total amount row
            orderItemsContainer.appendChild(advancePaidRow);

            // Add the row for balance (Total Amount - Advance Paid)
            const balanceRow = document.createElement('tr');
            balanceRow.innerHTML = `
                <td colspan="4" style="text-align:right;"><strong>Balance</strong></td>
                    <td colspan="2">
                    <span id="balance">₦${balance.toLocaleString()}</span>
                    </td>
                `;

            // Add the balance row to the table
            orderItemsContainer.appendChild(balanceRow);




        }
    } catch (error) {
        console.error('Error fetching orders:', error);
    }
}

function togglePaymentSchedule(orderId) {
    const scheduleRow = document.getElementById(`schedule-${orderId}`);
    scheduleRow.style.display = scheduleRow.style.display === 'none' ? '' : 'none';
}

document.addEventListener('DOMContentLoaded', fetchOrders);

