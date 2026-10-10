frappe.ui.form.on("WhatsApp Notifications", {
	refresh(frm) {
		if (!frm.doc.test_phone) {
			return;
		}
		frm.add_custom_button(__("Send Test"), () => {
			const send = () => {
				frappe.call({
					method: "qota.events.whatsapp_notices.send_test_message",
					args: { phone: frm.doc.test_phone },
					freeze: true,
					callback(response) {
						if (response.message) {
							frappe.msgprint(response.message);
						}
					},
				});
			};
			if (frm.is_dirty()) {
				frm.save().then(send);
			} else {
				send();
			}
		});
	},
});
