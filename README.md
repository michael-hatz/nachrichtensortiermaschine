#
Nachrichtensortiermaschine – An Email-Based RSS Reader  
![Nachrichtensortiermaschine](https://schmalenstroer.net/nachrichtensortiermaschine.png "Nachrichtensortiermaschine")

The **Nachrichtensortiermaschine** is an email-based RSS reader that integrates seamlessly with your mail program!  

## Why the Name?  
It's German for "news sorting machine"—and that's exactly what it does!  

## Features  
- 📩 Read your news directly in your inbox.  
- 🔍 Filter out topics you don't want to see.  
- 🗂 Build a searchable archive of everything you've read.  
- 🌍 Access it anywhere you can check your email.  

## Installation  
Run:  
```bash
docker pull mschfr/nachrichtensortiermaschine:20250411  
docker run -d -p 5000:5000 --name nachrichtensortiermaschine -v myconfig:/app/data mschfr/nachrichtensortiermaschine:20250411
```  
Then, visit **127.0.0.1:5000** (or your custom IP) to access the management interface.  

1. Enter your email settings.  
2. Subscribe to your favorite feeds.  
3. *(Optional)* Set up filters to remove unwanted content.  

## What It Does  
- 📧 Sends an email for every new item in your feeds.  
- 📂 Automatically sorts emails into folders.  
- 📰 Retrieves full text from truncated feeds.  
- 🚫 Filters out unwanted content.  
- **Read-Later Functionality**: Send links to a special address and receive the full-text article via email.  
- **Read-Later Folder**: Move articles into a special folder and get them compiled as an **ePub** (for your eBook reader) or a **text file**.  

## Additional Tips & Customization  
- **📬 Use a separate mail account**: Nachrichtensortiermaschine shouldn't delete anything, but it's cleaner to keep it separate from your main inbox.  
- **📥 Read-Later requires a dedicated mailbox**: You'll need a separate email address for storing articles (e.g., an *Artikelpostfach*). If you don’t have one, consider running a second Docker container with a mail server or set up filtering to direct mails into a specific subfolder.  
- **🔖 Bookmarklet available!** In the GitHub repository, you’ll find a bookmarklet—save it to your bookmarks bar to send the current webpage to your Read-Later folder in one click.  
- **📱 Mobile-friendly**: Use "Share to → Mail app" on mobile devices to send articles.  
- **⏳ Feeds update every hour by default**: You can modify this using `crontab -e` to adjust the cron job for `nsm.py`. Be mindful of server load.  
- **⚙️ Adjust Read-Later sync frequency**: You can configure how often `pocket-ersatz.py` checks for new emails.  
- **📅 Set digest delivery times**: Customize when and how often you receive a summary of your Read-Later folder.  
- **🛑 Filtering**: By default, filtering checks if the keyword appears in the email subject or article headline. If you prefer, you can modify `nsm.py` to search the full email text, though this may cause excessive blocking.  
- **📩 Works well with newsletters & mailing lists**: It’s not just for RSS feeds! Subscribe to newsletters for an even richer experience.  
- **🐍 No Docker? No problem!** Nachrichtensortiermaschine runs on plain Python. Feel free to use the files as-is and deploy them however you like.  
- **🛠️ Fork it, modify it, build on it!** You’re free to edit the code, repurpose it, or integrate it into your own projects. If you create something cool, let me know—I might "steal" your features back! 😉  

## Why Use It?  
- 📨 Read news using your favorite email program on any device.  
- 🔕 **Take control of your news**—filter out unwanted topics (e.g., Elon Musk, soccer, Taylor Swift, Kardashians, the Olympics, or Apple news).  
- 📜 **Build a full-text searchable archive** of everything you've read—stored in your personal email account.  
- 🚫 **No ads, no tracking, no commercialization.**  
- 📤 **"Built-in social"**—forward interesting articles to anyone via email.  
- 🌐 **Works offline**—download emails and read anywhere.  
- 🔄 **Easy to switch**—export your feeds or switch to other mail-based feed readers like RSS2Email. Since emails are stored in your inbox, you can use standard tools to manage them however you like.  

---

✅ **Enjoy reading your news—your way!** 

