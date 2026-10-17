# Greenshift website - Python backend

One small Python program (`server.py`) that:

1. Serves your website (the `public/` folder).
2. Receives the enquiry form and saves every enquiry to a database file (`greenshift.db`).
3. Emails your team a notification, and emails the customer a confirmation if they gave an email address (see Part 2 for how email works on free hosting).
4. Gives staff a private way to view all saved enquiries.

It uses **only what comes built into Python**. There is nothing to `pip install` and no downloads, so it does not depend on your internet speed once Python itself is installed.

## What is in the folder

| File | What it is |
|---|---|
| `server.py` | The whole backend |
| `public/index.html` | Your website (the form already talks to the backend) |
| `view_enquiries.py` | Prints saved enquiries, or exports them to a spreadsheet file |
| `.env.example` | Template for your passwords and settings |
| `requirements.txt` | Intentionally empty; some hosts expect the file to exist |
| `.gitignore` | Stops your passwords being uploaded to GitHub by accident |

---

## Part 1: Run it on your own computer

### Step 1: Check whether Python is installed

Open a terminal:
- **Windows:** press the Windows key, type `cmd`, press Enter.
- **Mac:** press Cmd+Space, type `Terminal`, press Enter.

Type this and press Enter:

- Windows: `python --version`
- Mac: `python3 --version`

If it prints something like `Python 3.12.4`, you are fine (any version from 3.8 up works). Go to Step 3.

If Windows opens the Microsoft Store or says "Python was not found", try `py --version`. If that also fails, do Step 2.

### Step 2: Install Python (only if Step 1 failed)

1. Go to **python.org/downloads** and click the big yellow Download button.
2. Run the installer. **On the first screen, tick the box "Add python.exe to PATH"** (Windows). This is the step people miss.
3. Click Install Now, wait, then Close.
4. **Close your terminal and open a new one**, then repeat Step 1.

### Step 3: Unzip and open the folder in the terminal

1. Unzip `greenshift-python.zip` (Windows: right-click, Extract All. Mac: double-click).
2. In the terminal, move into the folder. Type `cd ` (with a space after it), drag the `greenshift-python` folder into the terminal window, and press Enter.
3. Check you are in the right place: type `dir` (Windows) or `ls` (Mac). You should see `server.py` in the list.

### Step 4: Create a Gmail App Password

(This is for running on your own computer. Online you will use Resend instead; see Part 2. You can also skip email entirely while testing locally: enquiries are still saved.)

Gmail will not let programs sign in with your normal password. You need a special 16-letter "App Password":

1. Go to **myaccount.google.com** and click **Security**.
2. Make sure **2-Step Verification** is ON (set it up with your phone if not).
3. Go to **myaccount.google.com/apppasswords**.
4. Type a name such as `Greenshift website`, click **Create**, and copy the 16-letter code. You cannot view it again later.

### Step 5: Create your `.env` file

1. In the folder, make a copy of `.env.example` and name the copy exactly `.env`.
   - Windows: if you cannot see the extension, open the folder's View menu and tick "File name extensions", so you do not end up with `.env.txt`.
   - Mac: files starting with a dot are hidden in Finder; press Cmd+Shift+. to show them.
2. Open `.env` in Notepad or TextEdit and fill it in:

```
GMAIL_USER=Greenshiftrenewableenergy@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
NOTIFY_EMAIL=Greenshiftrenewableenergy@gmail.com
ADMIN_KEY=make-up-a-long-random-phrase
```

Paste your own App Password. Spaces in it are fine. Save the file.

### Step 6: Start it

- Windows: `python server.py` (or `py server.py`)
- Mac: `python3 server.py`

You should see:

```
Greenshift backend running on http://localhost:3000
```

Leave this window open. Closing it stops the website. To stop it yourself, press **Ctrl+C**.

### Step 7: Test it

1. Open a browser and go to **http://localhost:3000**. That is your website.
2. Fill in the enquiry form and send it. You should see a green success message.
3. Within a few seconds, an email should arrive at `NOTIFY_EMAIL`. If you typed your own email into the form, you also get the customer confirmation.

If no email arrives, look at the terminal window. A line starting `Email send failed` tells you why. The most common cause is a typo in the App Password, or 2-Step Verification not being switched on. Your enquiry is saved either way.

### Step 8: See your saved enquiries

Open a **second** terminal in the same folder (leave the first one running) and run:

- Windows: `python view_enquiries.py`
- Mac: `python3 view_enquiries.py`

To get a spreadsheet you can open in Excel:

```
python view_enquiries.py --csv leads.csv
```

Times are in UTC; Nigeria is one hour ahead.

---

## Part 2: Put it online (free)

You do not need a domain. Hosts give you a free web address, and you can add your own domain later.

**Read this first: two limits of free hosting.**
1. **Free hosts block normal email ports.** Render's free plan blocks the ports Gmail uses (25, 465, 587), so the Gmail setup from Part 1 will NOT work online. Online, this app sends email through **Resend**, which works over the normal web port. It is free (up to 100 emails a day).
2. **Free hosts forget saved files.** The database (`greenshift.db`) is wiped whenever the site restarts, redeploys or wakes from sleep. So online, **the notification email is your record of every enquiry. Do not delete those emails.** As a last resort, if an email cannot be sent, the full enquiry is written to the Logs tab in Render.

### Step 1: Get a Resend account and API key (5 minutes)

1. Go to **resend.com** and sign up **using the email address that should receive enquiries** (for example `Greenshiftrenewableenergy@gmail.com`). This matters: until you have your own domain, Resend only delivers to the address you signed up with.
2. Confirm your email address when Resend asks.
3. In the Resend dashboard open **API Keys** and click **Create API Key**. Name it `greenshift`, choose **Sending access**, and create it.
4. Copy the key (it starts with `re_`) into Notepad. You cannot see it again later.

### Step 2: Put the code on GitHub

1. Create an account at **github.com**.
2. Click **+** (top right), then **New repository**. Name it `greenshift-website`, leave everything else as it is, and click **Create repository**.
3. On the new empty repository page, click **uploading an existing file**.
4. Drag in **everything inside the `greenshift-python` folder**: `server.py`, `view_enquiries.py`, `requirements.txt`, `README.md`, `.env.example`, `.gitignore`, and the whole `public` folder.
5. **Do not upload `.env`** (your real passwords). Click **Commit changes**.
6. Click into the `public` folder on GitHub and check that `index.html` is inside it.

### Step 3: Create the web service on Render

1. Sign up at **render.com** (the "Sign up with GitHub" button is easiest).
2. Click **New +**, then **Web Service**, then choose your `greenshift-website` repository. If it is not listed, click "Configure account" and allow Render to see it.
3. Fill in the form (labels may differ slightly):
   - **Name:** `greenshift-website` (this becomes part of your web address)
   - **Language:** Python 3
   - **Branch:** `main`
   - **Root Directory:** leave blank
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python server.py`
   - **Instance Type:** Free
4. Scroll to **Environment Variables** and add these three. Do **not** add PORT; Render sets it.

| Key | Value |
|---|---|
| `RESEND_API_KEY` | the key from Resend (starts with `re_`) |
| `NOTIFY_EMAIL` | the SAME email address you signed up to Resend with |
| `ADMIN_KEY` | a long phrase you make up |

5. Click **Create Web Service**. Watch the log scroll; after 1 to 3 minutes the status changes to **Live**, and the log shows `Greenshift backend running on ...`.
6. Your web address is shown at the top of the page, something like `https://greenshift-website.onrender.com`. Open it.

### Step 4: Test the live site

1. Open your web address and submit the enquiry form.
2. You should see the green success message, and an email titled "New enquiry: ..." should reach `NOTIFY_EMAIL` within a minute. Check Spam too.
3. If no email arrives, open your service in Render and click **Logs**. Look for a line starting `Email send failed` (it says why) and a line starting `LEAD #` (the full enquiry, so nothing is lost).

### Things to know once it is live

- **Sleeping:** after 15 minutes without visitors the site goes to sleep, and the next visitor waits about a minute while it wakes up.
- **Customer confirmation emails are switched off for now.** Resend will only send to your own address until you own a domain and verify it with them. Notification emails to you work now, and each one has the customer as Reply-To, so you can reply to them straight from your inbox.
- **When you get a domain:** add it at resend.com/domains and follow their DNS steps, then add one more variable in Render: `MAIL_FROM` set to an address on that domain, for example `enquiries@yourdomain.com`. Customer confirmations then switch on automatically. To point the domain at the website itself, use Render's **Settings**, then **Custom Domains**.
- **Keeping enquiries permanently** needs a paid Render plan with a disk, or a hosted database. For a small business, saving the notification emails is the simplest approach.

### Viewing enquiries on the live site

Online, the saved list resets, so rely on your emails. If you still want to look, use a terminal (on Windows 10 and 11, `curl` is built in):

```
curl https://YOUR-SITE.onrender.com/api/enquiries -H "x-admin-key: YOUR_ADMIN_KEY"
```

---

## Troubleshooting

| What you see | What to do |
|---|---|
| `python` is "not recognized" / opens the Microsoft Store | Try `py server.py`. If that fails, reinstall Python and tick "Add python.exe to PATH". |
| `Could not start on port 3000` | Another program uses that port. Add `PORT=3001` on its own line in `.env`, start again, and open `http://localhost:3001`. |
| Form shows "couldn't reach the server" and opens your email app | The page was opened as a plain file instead of through the server. Start `server.py` and use `http://localhost:3000`. |
| Form says "Too many enquiries from this device" | Built-in spam protection: 10 submissions per 15 minutes per visitor. Wait, or restart the server. |
| Emails do not arrive (on your computer) | Check the terminal for `Email send failed`. Re-create the Gmail App Password, check there are no typos in `.env`, and look in Spam. |
| Emails do not arrive (online) | Open Logs in Render. `Resend answered 403 ... testing emails` means `NOTIFY_EMAIL` is not the address you signed up to Resend with. `401` means the API key is wrong. The `LEAD #` line holds the enquiry either way. |

## Technical notes

- Spam protection: 10 submissions per visitor per 15 minutes, requests over 20 KB are rejected, and every field is checked on the server.
- Staff key checking is constant-time; with no `ADMIN_KEY` set, the staff view is switched off entirely.
- Only files inside `public/` can ever be downloaded. `server.py`, `.env` and the database are not reachable from a browser.
