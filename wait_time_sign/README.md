# Wait Time Sign for Tufty 2350

A little theme-park wait-time app for my Tufty 2350. This is the color version
of my Badger project, with park artwork, favorites, and a few small animations.

I wanted to keep it simple: choose a park, see the waits, and save the rides
you care about. Updates happen in the background, so you can keep using it.

## Install

This runs on the Pimoroni Tufty 2350 with Badgeware firmware.

1. Plug the Tufty into the computer with a USB data cable.
2. Double-tap RESET. A drive called TUFTY should appear.
3. Copy the `wait_time_sign` folder into its `apps` folder.
4. Safely eject the drive. Press RESET once if the menu doesn't return.
5. Select Wait Time Sign in the launcher and press B.

For an update, copy the app files into the existing `apps/wait_time_sign`
folder. Keep your existing `icon.png`, `secrets.py`, and saved state.

Wi-Fi needs to be set up in the Tufty's `secrets.py`, using `WIFI_SSID` and
`WIFI_PASSWORD`. Keep the file you already have if Wi-Fi is working. No API
key is needed.

## Buttons

| Button | Ride sign, board, and favorites | Choosing a park |
| --- | --- | --- |
| A | Choose a park | Go back |
| B tap | Switch between sign, board, and favorites | Next resort group |
| B hold | Refresh the waits | Release and tap B to change resort |
| C | Save or remove a favorite on the sign; open a ride from a list | Choose this park |
| Up / Down | Previous or next ride | Previous or next park |
| Home | Return to the launcher | Return to the launcher |

Hold B for about a second to refresh. Leave at least a minute between update
attempts. A short tap changes the view.

## Parks

There are twelve parks to choose from:

| Resort | Parks |
| --- | --- |
| Walt Disney World | Magic Kingdom, EPCOT, Hollywood Studios, Animal Kingdom |
| Disneyland Resort | Disneyland, California Adventure |
| Universal Orlando | Universal Studios Florida, Islands of Adventure, Epic Universe, Volcano Bay |
| Universal Hollywood | Universal Studios Hollywood |
| SeaWorld | SeaWorld Orlando |

## Reading the screen

Waits refresh when the app opens and about every five minutes afterward.
The ride sign or board stays on screen while it updates, with one small
shooting star moving through the artwork or status area.

The wait colors are mint for 0–20 minutes, amber for 21–45, and coral for 46
or more. A zero means a reported zero-minute wait. `--` means the wait isn't
available. `CLOSED` is the ride's reported status, not the park's hours.

If a ride name won't fit, the first two lines stay still and the third line
scrolls through the rest. It pauses at both ends. Changing rides starts it
over. Board names use two lines; press C to open the full ride sign.

### Wait-change arrows

A green down arrow means the wait got shorter. A coral up arrow means it got
longer. The number is the difference in minutes: a change from 60 to 45 shows
a down arrow with 15.

These appear after two successful live updates for the selected park. They
clear when you change parks or an update fails. Closed rides, missing waits,
unchanged waits, and readings that aren't newer don't get an arrow. They show
what changed between readings, not what the wait will do next.

### Battery

The small battery icon shows an approximate charge level. It turns coral and
says LOW at 15% or below. While plugged in, it says USB. `--%` means a battery
reading isn't available.

On battery, the screen dims after 30 seconds without a button press. The
first press wakes it. Scrolling and the shooting star pause while it's dimmed.

### Saved waits and seasonal rides

If an update fails, the app keeps the last saved waits and marks them SAVED.
The update time is in UTC. Your selected park, favorites, and saved readings
stay in `/state/wait_time_sign` between uses.

Known holiday versions have a small SEASONAL label. Regular and seasonal
versions stay separate, with their own waits and closed statuses. The label
identifies the seasonal version; it doesn't mean that version is running today.

## Artwork

All twelve park pictures and both shooting-star effects are in one `art.bin`,
like my Halloween app. The font and its license sit beside it. There is no
`art` folder to install.

Keep `art.bin`, the app's Python files, and `display.af` together when copying
an update.

## Credits and license

Powered by [Queue-Times.com](https://queue-times.com/).

Poppins comes from Pimoroni's Badgeware font release; its license is in
`DISPLAY-OFL.txt`. Mona Sans is supplied with Badgeware.

GPL-3.0-only. Copyright (c) 2026 [Chris Parrish](https://github.com/KK4TSS/).
See [LICENSE](LICENSE).

## Tip jar

If you like what I'm making and want to leave a tip, [here's my PayPal](https://www.paypal.com/donate/?hosted_button_id=EQTU33JHZ5TJ6). No pressure. Tips are optional and help support more tinkering and new projects. Thank you! Thanks for checking out my projects.
