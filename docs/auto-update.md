# Auto-update from GitHub

Push to `main` on GitHub → the server runs the
new code within about 5 minutes. Nothing to do
on the server.

## What happens

Every 5 minutes the server:

1. Checks GitHub for a new commit on `main`.
2. Waits until GitHub's tests for that commit are
   finished (the green ✓ on the commit).
3. Tests passed → updates the code and installs
   new Python packages if `requirements.txt`
   changed.
4. Runs a quick self-test. If the new code is
   broken, it **rolls back** to the previous
   version.
5. Applies changed timer/service files.
6. Tells you in Telegram:
   - 🔄 `Bot updated to abc1234: <commit message>`
   - ⚠️ `Not deployed: … failed its GitHub tests`
   - ❌ `Update … broke the bot, so it was rolled back`

A failed or rolled-back commit gives one notice,
not one every 5 minutes. The next commit you push
is tried again normally.

## Why the server pulls

The server fetches from GitHub, instead of GitHub
logging in to the server. So:

- no SSH key or server address stored on GitHub
- no extra open ports
- works even if the server is behind a firewall

The cost is a delay of up to 5 minutes.

## Safety

- The updater itself is copied to
  `/usr/local/sbin` when you run `install.sh`. A
  push can't change what runs as root.
- The bot always runs as the locked-down
  `tweetbot` user.
- Only commits that passed the GitHub tests are
  deployed.

Because of the first point, changes to
`deploy/install.sh`, `deploy/auto-update.sh` or the
`*-update.*` files need one manual run:

```bash
sudo /opt/telegram-tweet-notification/deploy/install.sh
```

The Telegram notice reminds you when that's
needed.

## Rules of thumb

- Make changes on GitHub (or push from your
  computer), **not** by editing files in
  `/opt/telegram-tweet-notification`. Local edits
  there are overwritten on the next update.
- Settings stay in
  `/etc/telegram-tweet-notification.env`. Updates
  never touch that file.
- Want to try something without deploying? Push it
  to another branch. Only `main` is deployed.

## Commands

See update activity:

```bash
journalctl -u telegram-tweet-notification-update -n 30
```

Update right now instead of waiting:

```bash
sudo systemctl start telegram-tweet-notification-update
```

Pause / resume auto-updates:

```bash
sudo systemctl stop telegram-tweet-notification-update.timer
sudo systemctl start telegram-tweet-notification-update.timer
```

Go back to an older version (pause auto-updates
first, or it moves forward again):

```bash
cd /opt/telegram-tweet-notification
sudo git log --oneline -5
sudo git reset --hard <commit>
```

Better: revert the commit on GitHub and push. The
server follows within 5 minutes.

## Private repo

For a private repo the server needs read access:

1. On the server: `sudo ssh-keygen -t ed25519 -f /root/.ssh/github_deploy -N ""`
2. GitHub → repo → Settings → Deploy keys → Add
   the contents of `/root/.ssh/github_deploy.pub`
   (read-only).
3. Switch the remote:
   `sudo git -C /opt/telegram-tweet-notification remote set-url origin git@github.com:Summerinfluenza/telegram-tweet-notification.git`
4. Tell ssh to use the key, in `/root/.ssh/config`:
   ```
   Host github.com
     IdentityFile /root/.ssh/github_deploy
   ```
5. GitHub's test status can't be read without a
   token, so set `AUTO_UPDATE_REQUIRE_TESTS=false`
   in the settings file. The self-test and rollback
   still protect you.
