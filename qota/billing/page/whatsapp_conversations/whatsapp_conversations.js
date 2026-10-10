frappe.provide("qota");

frappe.pages["whatsapp-conversations"].on_page_load = function (wrapper) {
	$(wrapper).addClass("qota-wa-page");
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Conversations"),
		single_column: true,
	});
	wrapper.conversation_page = new qota.WhatsAppConversations(page);
};

frappe.pages["whatsapp-conversations"].on_page_show = function (wrapper) {
	const view = wrapper.conversation_page;
	if (!view) return;
	view.fit();
	if (!view.timer) {
		view.refresh_list(true);
		view.timer = setInterval(() => view.refresh_list(true), 10000);
	}
};

qota.WhatsAppConversations = class WhatsAppConversations {
	constructor(page) {
		this.page = page;
		this.selected = null;
		this.rows = [];
		this.query = "";
		this.signature = "";
		this.timer = null;
		this.make();
		this.refresh_list();
		this.timer = setInterval(() => this.refresh_list(true), 10000);
		$(document).on("page-change.qota-wa", () => {
			if (frappe.get_route()[0] !== "whatsapp-conversations" && this.timer) {
				clearInterval(this.timer);
				this.timer = null;
			}
		});
		$(window).on("resize.qota-wa", () => this.fit());
	}

	make() {
		this.page.page_head.hide();
		this.page.main.html(`
			<style>
				.qota-wa-page.page-container { background: #fff; }
				.qota-wa-page .page-head { display: none !important; }
				.qota-wa-page .page-body,
				.qota-wa-page .page-wrapper,
				.qota-wa-page .page-content,
				.qota-wa-page .layout-main,
				.qota-wa-page .layout-main-section-wrapper,
				.qota-wa-page .layout-main-section {
					padding: 0 !important;
					margin: 0 !important;
					border: 0 !important;
					box-shadow: none !important;
					background: transparent;
					max-width: none !important;
					width: 100% !important;
					min-height: 0;
				}
				.qota-wa-page .layout-main-section-wrapper { flex: 1 1 auto !important; }
				.qota-wa {
					display: flex;
					height: 32rem;
					background: #fff;
					color: #111b21;
					font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
					overflow: hidden;
					border-top: 1px solid #e9edef;
				}
				.qota-wa-list {
					width: 30%;
					min-width: 300px;
					max-width: 440px;
					display: flex;
					flex-direction: column;
					background: #fff;
					border-right: 1px solid #e9edef;
				}
				.qota-wa-list-head { padding: 10px 16px 6px; background: #fff; flex: none; }
				.qota-wa-list-head h2 {
					margin: 6px 0 10px;
					font-size: 22px;
					font-weight: 600;
					color: #111b21;
					line-height: 1.2;
				}
				.qota-wa-search {
					width: 100%;
					height: 35px;
					border: 0;
					border-radius: 8px;
					background-color: #f0f2f5;
					padding: 0 12px 0 36px;
					outline: none;
					font-size: 14px;
					color: #111b21;
					background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%2354656f' viewBox='0 0 24 24'><path d='M15.5 14h-.8l-.3-.3a6.5 6.5 0 1 0-.7.7l.3.3v.8l5 5 1.5-1.5-5-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z'/></svg>");
					background-repeat: no-repeat;
					background-position: 12px center;
				}
				.qota-wa-search::placeholder,
				.qota-wa-compose textarea::placeholder { color: #667781; }
				.qota-wa-chats, .qota-wa-msgs { scrollbar-width: thin; scrollbar-color: rgba(17, 27, 33, 0.25) transparent; }
				.qota-wa-chats { flex: 1; overflow: auto; }
				.qota-wa-item {
					display: flex;
					gap: 15px;
					width: 100%;
					text-align: left;
					border: 0;
					background: #fff;
					padding: 0 0 0 13px;
					cursor: pointer;
					align-items: center;
				}
				.qota-wa-item:hover { background: #f5f6f6; }
				.qota-wa-item.active,
				.qota-wa-item.active:hover { background: #f0f2f5; }
				.qota-wa-avatar {
					width: 49px;
					height: 49px;
					border-radius: 50%;
					color: #fff;
					display: flex;
					align-items: center;
					justify-content: center;
					font-weight: 500;
					font-size: 17px;
					flex: 0 0 49px;
					letter-spacing: 0.2px;
				}
				.qota-wa-head .qota-wa-avatar { width: 40px; height: 40px; flex-basis: 40px; font-size: 15px; }
				.qota-wa-item-body {
					min-width: 0;
					flex: 1;
					padding: 12px 15px 12px 0;
					border-bottom: 1px solid #e9edef;
				}
				.qota-wa-item:hover .qota-wa-item-body,
				.qota-wa-item.active .qota-wa-item-body { border-bottom-color: transparent; }
				.qota-wa-item-top, .qota-wa-item-bottom { display: flex; align-items: center; gap: 8px; }
				.qota-wa-item-top { margin-bottom: 2px; }
				.qota-wa-name {
					font-size: 17px;
					font-weight: 400;
					flex: 1;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
					color: #111b21;
				}
				.qota-wa-item.has-unread .qota-wa-name { font-weight: 600; }
				.qota-wa-time { color: #667781; font-size: 12px; flex: none; }
				.qota-wa-item.has-unread .qota-wa-time { color: #25d366; }
				.qota-wa-preview {
					color: #667781;
					font-size: 14px;
					flex: 1;
					min-width: 0;
					display: flex;
					align-items: center;
					gap: 4px;
				}
				.qota-wa-preview-text {
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
					min-width: 0;
				}
				.qota-wa-badge {
					min-width: 20px;
					height: 20px;
					padding: 0 6px;
					border-radius: 10px;
					background: #25d366;
					color: #fff;
					font-size: 12px;
					font-weight: 600;
					line-height: 20px;
					text-align: center;
					flex: none;
				}
				.qota-wa-thread {
					flex: 1;
					min-width: 0;
					display: flex;
					flex-direction: column;
					background: #efeae2;
				}
				.qota-wa-head {
					display: flex;
					align-items: center;
					gap: 12px;
					height: 60px;
					padding: 0 16px;
					background: #f0f2f5;
					border-bottom: 1px solid #e9edef;
					flex: none;
				}
				.qota-wa-back {
					display: none;
					border: 0;
					background: transparent;
					padding: 0;
					cursor: pointer;
					color: #54656f;
				}
				.qota-wa-who { min-width: 0; line-height: 1.25; }
				.qota-wa-who strong {
					display: block;
					font-size: 16px;
					font-weight: 400;
					color: #111b21;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}
				.qota-wa-who span,
				.qota-wa-who a {
					display: block;
					color: #667781;
					font-size: 13px;
					overflow: hidden;
					text-overflow: ellipsis;
					white-space: nowrap;
				}
				.qota-wa-who a { color: #027eb5; text-decoration: none; }
				.qota-wa-who a:hover { text-decoration: underline; }
				.qota-wa-msgs {
					flex: 1;
					overflow: auto;
					padding: 12px 8% 16px;
					display: flex;
					flex-direction: column;
					background-color: #efeae2;
					background-image: radial-gradient(rgba(17, 27, 33, 0.045) 0.7px, transparent 0.7px);
					background-size: 18px 18px;
				}
				.qota-wa-day {
					align-self: center;
					margin: 8px 0 6px;
					background: #fff;
					color: #54656f;
					font-size: 12.5px;
					padding: 5px 12px 6px;
					border-radius: 8px;
					box-shadow: 0 1px 0.5px rgba(11, 20, 26, 0.13);
				}
				.qota-wa-bubble {
					max-width: 65%;
					margin-top: 2px;
					padding: 6px 7px 8px 9px;
					border-radius: 7.5px;
					box-shadow: 0 1px 0.5px rgba(11, 20, 26, 0.13);
					position: relative;
				}
				.qota-wa-bubble.is-group-start { margin-top: 10px; }
				.qota-wa-bubble.out { align-self: flex-end; background: #d9fdd3; }
				.qota-wa-bubble.in { align-self: flex-start; background: #fff; }
				.qota-wa-bubble.has-tail.in { border-top-left-radius: 0; }
				.qota-wa-bubble.has-tail.out { border-top-right-radius: 0; }
				.qota-wa-bubble.has-tail::before {
					content: "";
					position: absolute;
					top: 0;
					width: 8px;
					height: 13px;
				}
				.qota-wa-bubble.has-tail.in::before {
					left: -8px;
					background: #fff;
					clip-path: polygon(100% 0, 100% 100%, 0 0);
				}
				.qota-wa-bubble.has-tail.out::before {
					right: -8px;
					background: #d9fdd3;
					clip-path: polygon(0 0, 0 100%, 100% 0);
				}
				.qota-wa-bubble::after { content: ""; display: table; clear: both; }
				.qota-wa-text {
					white-space: pre-wrap;
					word-wrap: break-word;
					font-size: 14.2px;
					line-height: 19px;
					color: #111b21;
				}
				.qota-wa-meta {
					float: right;
					display: inline-flex;
					align-items: center;
					gap: 3px;
					margin: 4px 0 -6px 12px;
					position: relative;
					top: 4px;
					color: #667781;
					font-size: 11px;
					line-height: 15px;
					height: 15px;
					user-select: none;
				}
				.qota-wa-ticks { letter-spacing: -1px; color: #667781; }
				.qota-wa-ticks.read { color: #53bdeb; }
				.qota-wa-ticks svg { display: block; }
				.qota-wa-failed { color: #ea0038; font-size: 11px; letter-spacing: 0; }
				.qota-wa-compose {
					display: flex;
					gap: 8px;
					align-items: flex-end;
					padding: 10px 16px;
					background: #f0f2f5;
					flex: none;
					min-height: 62px;
				}
				.qota-wa-compose textarea {
					flex: 1;
					border: 0;
					border-radius: 8px;
					background: #fff;
					padding: 9px 12px;
					min-height: 42px;
					max-height: 120px;
					resize: none;
					outline: none;
					font: 15px/20px "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
					color: #111b21;
				}
				.qota-wa-send {
					width: 40px;
					height: 42px;
					border: 0;
					border-radius: 50%;
					background: transparent;
					color: #00a884;
					cursor: pointer;
					display: flex;
					align-items: center;
					justify-content: center;
					flex: none;
				}
				.qota-wa-send:hover { background: rgba(0, 168, 132, 0.1); }
				.qota-wa-intro, .qota-wa-empty {
					margin: auto;
					text-align: center;
					color: #667781;
					max-width: 32rem;
					padding: 2rem 1.5rem;
				}
				.qota-wa-mark {
					width: 88px;
					height: 88px;
					margin: 0 auto 16px;
				}
				.qota-wa-intro h3 {
					color: #41525d;
					font-weight: 300;
					font-size: 32px;
					margin: 0 0 12px;
				}
				.qota-wa-intro p { margin: 0; font-size: 14px; line-height: 20px; }
				.qota-wa-empty { padding: 2rem 1rem; font-size: 14px; }
				.qota-wa.is-empty .qota-wa-head,
				.qota-wa.is-empty .qota-wa-compose { display: none; }
				@media (max-width: 720px) {
					.qota-wa-list { width: 100%; max-width: none; min-width: 0; border-right: 0; }
					.qota-wa-thread { display: none; }
					.qota-wa.has-chat .qota-wa-list { display: none; }
					.qota-wa.has-chat .qota-wa-thread { display: flex; }
					.qota-wa-back { display: inline-flex; }
					.qota-wa-msgs { padding: 12px 16px 16px; }
					.qota-wa-bubble { max-width: 85%; }
				}
			</style>
			<div class="qota-wa is-empty">
				<aside class="qota-wa-list">
					<div class="qota-wa-list-head">
						<h2>${__("Conversations")}</h2>
						<input class="qota-wa-search" type="search" placeholder="${__("Search")}" autocomplete="off">
					</div>
					<div class="qota-wa-chats"></div>
				</aside>
				<section class="qota-wa-thread">
					<header class="qota-wa-head">
						<button type="button" class="qota-wa-back" aria-label="${__("Back")}">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
								<path d="M15 6 9 12l6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
							</svg>
						</button>
						<span class="qota-wa-avatar qota-wa-head-avatar"></span>
						<div class="qota-wa-who"></div>
					</header>
					<div class="qota-wa-msgs"></div>
					<form class="qota-wa-compose">
						<textarea rows="1" placeholder="${__("Write a reply")}"></textarea>
						<button type="submit" class="qota-wa-send" aria-label="${__("Send")}">
							<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
								<path d="M3.4 20.6 21 12 3.4 3.4l-.1 6.7L15.2 12 3.3 13.9z"/>
							</svg>
						</button>
					</form>
				</section>
			</div>
		`);
		this.root = this.page.main.find(".qota-wa");
		this.chats = this.page.main.find(".qota-wa-chats");
		this.head_avatar = this.page.main.find(".qota-wa-head-avatar");
		this.who = this.page.main.find(".qota-wa-who");
		this.msgs = this.page.main.find(".qota-wa-msgs");
		this.box = this.page.main.find("textarea");
		this.show_intro();
		this.page.main.find(".qota-wa-search").on("input", (event) => {
			this.query = event.target.value || "";
			this.render_list();
		});
		this.page.main.find(".qota-wa-back").on("click", () => this.close_chat());
		this.page.main.find(".qota-wa-compose").on("submit", (event) => {
			event.preventDefault();
			this.send();
		});
		this.box.on("keydown", (event) => {
			if (event.key === "Enter" && !event.shiftKey) {
				event.preventDefault();
				this.send();
			}
		});
		this.fit();
		requestAnimationFrame(() => this.fit());
	}

	fit() {
		if (!this.root[0]) return;
		const top = this.root[0].getBoundingClientRect().top;
		this.root.css("height", Math.max(420, window.innerHeight - top) + "px");
	}

	refresh_list(silent) {
		frappe.call({
			method: "qota.billing.page.whatsapp_conversations.whatsapp_conversations.list_conversations",
			callback: (response) => {
				this.rows = response.message || [];
				this.render_list();
				if (this.selected && silent) {
					this.open(this.selected, true);
				}
			},
		});
	}

	render_list() {
		const scroll = this.chats.scrollTop();
		const needle = this.query.trim().toLowerCase();
		const rows = this.rows.filter((row) => {
			if (!needle) return true;
			return [row.contact_name, row.phone, row.last_body].join(" ").toLowerCase().includes(needle);
		});
		this.chats.empty();
		if (!rows.length) {
			const empty = needle ? __("No conversations match the search.") : __("No conversations yet.");
			this.chats.append(`<div class="qota-wa-empty">${empty}</div>`);
			return;
		}
		rows.forEach((row) => {
			const title = row.contact_name || row.phone || "";
			const unread = parseInt(row.unread, 10) || 0;
			const button = $(`
				<button type="button" class="qota-wa-item ${row.name === this.selected ? "active" : ""} ${unread ? "has-unread" : ""}">
					<span class="qota-wa-avatar" style="background:${this.color_for(title)}">${frappe.utils.escape_html(this.initials(title))}</span>
					<span class="qota-wa-item-body">
						<span class="qota-wa-item-top">
							<span class="qota-wa-name">${frappe.utils.escape_html(title)}</span>
							<time class="qota-wa-time">${frappe.utils.escape_html(this.list_time(row.last_on))}</time>
						</span>
						<span class="qota-wa-item-bottom">
							<span class="qota-wa-preview">${this.list_ticks(row)}<span class="qota-wa-preview-text">${frappe.utils.escape_html(this.one_line(row.last_body))}</span></span>
							${unread ? `<span class="qota-wa-badge">${unread}</span>` : ""}
						</span>
					</span>
				</button>
			`);
			button.on("click", () => this.open(row.name));
			this.chats.append(button);
		});
		this.chats.scrollTop(scroll);
	}

	open(name, silent) {
		this.selected = name;
		this.root.addClass("has-chat").removeClass("is-empty");
		const near_bottom =
			this.msgs.scrollTop() + this.msgs.innerHeight() >= this.msgs.prop("scrollHeight") - 48;
		frappe.call({
			method: "qota.billing.page.whatsapp_conversations.whatsapp_conversations.thread",
			args: { conversation: name },
			callback: (response) => {
				if (this.selected !== name) return;
				const data = response.message || {};
				const header = data.conversation || {};
				const title = header.contact_name || header.phone || "";
				const route = header.subscriber
					? frappe.utils.get_form_link("Subscriber", header.subscriber)
					: "";
				const link = route
					? `<a href="${frappe.utils.escape_html(route)}">${frappe.utils.escape_html(header.subscriber)}</a>`
					: "";
				this.head_avatar.text(this.initials(title)).css("background", this.color_for(title));
				this.who.html(
					`<strong>${frappe.utils.escape_html(title)}</strong><span>${frappe.utils.escape_html(header.phone || "")}</span>${link}`
				);
				const messages = data.messages || [];
				const signature = messages
					.map((message) => [message.sent_on, message.status, message.body].join("\u0001"))
					.join("\u0002");
				if (silent && signature === this.signature) {
					this.render_list();
					return;
				}
				this.signature = signature;
				this.msgs.empty();
				let day = "";
				messages.forEach((message, index) => {
					const label = this.day_label(message.sent_on);
					const day_break = Boolean(label && label !== day);
					if (day_break) {
						day = label;
						this.msgs.append(`<div class="qota-wa-day">${frappe.utils.escape_html(label)}</div>`);
					}
					const side = message.direction === "Outgoing" ? "out" : "in";
					const previous = messages[index - 1];
					const tail = day_break || !previous || previous.direction !== message.direction;
					this.msgs.append(`
						<div class="qota-wa-bubble ${side} ${tail ? "has-tail is-group-start" : ""}">
							<span class="qota-wa-text">${frappe.utils.escape_html(message.body || "")}</span>
							<span class="qota-wa-meta"><time>${frappe.utils.escape_html(this.clock(message.sent_on))}</time>${this.status_html(message)}</span>
						</div>
					`);
				});
				if (!silent || near_bottom) {
					this.msgs.scrollTop(this.msgs.prop("scrollHeight"));
				}
				this.render_list();
			},
		});
	}

	close_chat() {
		this.selected = null;
		this.signature = "";
		this.root.removeClass("has-chat").addClass("is-empty");
		this.who.empty();
		this.head_avatar.text("").css("background", "");
		this.show_intro();
		this.render_list();
	}

	show_intro() {
		this.msgs.html(`
			<div class="qota-wa-intro">
				<div class="qota-wa-mark" aria-hidden="true">
					<svg width="88" height="88" viewBox="0 0 88 88" fill="none">
						<rect x="6" y="16" width="50" height="36" rx="12" fill="#d9fdd3"/>
						<rect x="30" y="34" width="52" height="38" rx="12" fill="#ffffff" stroke="#d1d7db"/>
					</svg>
				</div>
				<h3>${__("Conversations")}</h3>
				<p>${__("When someone writes to the number, the message shows up here.")}</p>
			</div>
		`);
	}

	send() {
		const body = this.box.val();
		if (!this.selected || !String(body || "").trim()) {
			return;
		}
		frappe.call({
			method: "qota.billing.page.whatsapp_conversations.whatsapp_conversations.send_reply",
			args: { conversation: this.selected, body },
			freeze: true,
			callback: () => {
				this.box.val("");
				this.open(this.selected);
				this.refresh_list(true);
			},
		});
	}

	status_html(message) {
		if (message.direction !== "Outgoing") return "";
		if (message.status === "Failed") {
			return `<span class="qota-wa-failed">${__("Failed")}</span>`;
		}
		if (message.status === "Read") return `<span class="qota-wa-ticks read">✓✓</span>`;
		if (message.status === "Delivered") return `<span class="qota-wa-ticks">✓✓</span>`;
		if (message.status === "Sent") return `<span class="qota-wa-ticks">✓</span>`;
		if (message.status === "Pending") return this.pending_html();
		return "";
	}

	list_ticks(row) {
		if (row.last_direction !== "Outgoing") return "";
		return this.status_html({ direction: "Outgoing", status: row.last_status });
	}

	pending_html() {
		return `<span class="qota-wa-ticks"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 4.6V8.2l2.3 1.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></span>`;
	}

	initials(name) {
		const text = String(name || "").trim();
		if (!text) return "?";
		if (/^[+\d]/.test(text)) {
			const digits = text.replace(/\D/g, "");
			return digits.slice(-2) || "?";
		}
		const words = text.split(/\s+/).filter(Boolean);
		if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
		return (words[0][0] + words[1][0]).toUpperCase();
	}

	color_for(name) {
		const palette = ["#00a884", "#53bdeb", "#ff8a65", "#7e57c2", "#00897b", "#ef5350", "#5c6bc0", "#8d6e63"];
		const text = String(name || "");
		let hash = 0;
		for (let i = 0; i < text.length; i++) hash = (hash + text.charCodeAt(i)) % palette.length;
		return palette[hash];
	}

	one_line(value) {
		return String(value || "").replace(/\s+/g, " ").trim();
	}

	list_time(value) {
		if (!value || typeof moment === "undefined") return "";
		const when = moment(value);
		if (!when.isValid()) return "";
		if (when.isSame(moment(), "day")) return when.format("HH:mm");
		if (when.isSame(moment().subtract(1, "day"), "day")) return __("Yesterday");
		return when.format("DD/MM/YYYY");
	}

	day_label(value) {
		if (!value || typeof moment === "undefined") return "";
		const when = moment(value);
		if (!when.isValid()) return "";
		if (when.isSame(moment(), "day")) return __("Today");
		if (when.isSame(moment().subtract(1, "day"), "day")) return __("Yesterday");
		return when.format("DD/MM/YYYY");
	}

	clock(value) {
		if (!value || typeof moment === "undefined") return "";
		const when = moment(value);
		return when.isValid() ? when.format("HH:mm") : "";
	}
};
