# Testing Relay with Coexistence

Coexistence means the business keeps using the **WhatsApp Business app** on the phone, and Relay's AI replies through the Cloud API **only during AI hours**. If the owner replies from the phone, the AI pauses for that chat.

## How Relay behaves

For each new customer message, Relay checks, in this order:

1. **Automation off, or chat taken over?** Then it stays silent.
2. **Outside AI hours?** Then it stays silent: no AI call, no draft. The message is still logged in the Inbox.
3. **Otherwise** it follows the mode as before:
   - **Manual:** writes a suggestion.
   - **Approval:** queues a draft for you to approve.
   - **Automatic:** sends the reply, with all the existing safety checks.

When the owner replies from the phone, Meta sends an `smb_message_echoes` webhook. Relay then:
- logs the reply in the chat as a team message
- marks the chat as **taken over**
- drops any pending AI draft for that chat

That pause ends on its own after **"Pause the AI after you reply from the phone"** (Automation page, default 120 minutes).

A takeover you click **inside Relay** never expires. It lasts until you press "Resume AI".

AI hours are set under **Automation → AI hours**, in the workspace time zone. If the end time is before the start time, the range runs overnight: `22:00–06:00` on Monday covers Monday night through Tuesday 06:00.

## Level 1: Test mode (no Meta, works today)

Requires `DEBUG=True` in `backend/.env` and a phone number ID saved on the Integrations page. Then:

1. Start the backend and frontend (see `.claude/launch.json`) and sign in.
2. **Automation:**
   - Pick **Approval** mode.
   - Turn on **"Only let the AI reply during these hours"**.
   - Set today to a range that **includes** the current time.
3. **Inbox → Simulate message → Customer message:** inject one. **Expect:** an AI draft appears.
4. **Simulate message → Owner reply from phone:** use the **same WhatsApp number**. **Expect:**
   - the owner's text appears as a team message
   - the chat shows as taken over
   - the draft disappears
5. Inject another **customer message** for that number. **Expect:** no draft, because the AI is paused.
6. On the Automation page, set the pause to `1` minute, wait a minute, and inject a customer message. **Expect:** the AI drafts again.
7. Change today's AI hours so they **exclude** the current time, then inject a customer message. **Expect:** the message is logged and no draft is created.

Simulated events never mark the real webhook as healthy. Replies sent in Automatic mode still go through the real Cloud API.

## Level 2: Real Cloud API number (works today, no coexistence)

Use the number that's already connected. Real customer messages from a phone listed as a test recipient go through the same AI-hours logic. The owner-reply pause can't happen yet, because a Cloud-API-only number has no phone app. Use the simulator's **Owner reply from phone** for that.

## Level 3: Real coexistence (needs Meta setup)

Do these steps by hand in Meta:

1. **Webhook fields:** in the Meta app's WhatsApp → Configuration, also subscribe to **`smb_message_echoes`** next to `messages`. Without it, phone replies never reach Relay.
2. **Embedded Signup configuration:**
   - Create one with the **WhatsApp Business app onboarding (coexistence)** option enabled.
   - Put its config ID and the app ID in `backend/.env`; Integrations then shows "Connect with Meta".
   - The app can stay in **development mode**. Use a WhatsApp Business app number you own, signed in with an account that has a role on the Meta app.
   - Check first that Meta allows coexistence onboarding in development mode. If it doesn't, use a Solution Partner sandbox.
3. **Scan the QR code** from the WhatsApp Business app when Embedded Signup asks. The number then works in both the app and Relay.
4. **Repeat the Level 1 checks with real phones:**
   - A second phone acts as the customer.
   - The business phone acts as the owner.
   - When the owner replies on the business phone, the Inbox shows it and the AI pauses for that chat.
5. **Record this flow** for App Review: connect, customer message, AI reply, owner reply from the phone, AI pauses.

## Not built yet (by design, for now)

- **History sync** (`history` webhook): importing past phone-app chats needs Tech Provider access.
- **"Reply only if the owner hasn't answered within N minutes"**.
- **Photos or voice notes the owner sends from the phone:** these show as a placeholder only. Media isn't downloaded.
