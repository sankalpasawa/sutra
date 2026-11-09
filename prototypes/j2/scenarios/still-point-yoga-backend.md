Create the design documents (PRD, HLD and LLD) and then build the website with a small backend for Still Point Yoga, a small yoga studio at 4th Floor, 22 Church Street, Bengaluru 560001.

The page shows the name Still Point Yoga and the address as text, with no embedded map.

The weekly class list has five classes, each with day, time and price in rupees:
Monday 7:00 am Gentle Flow 500
Tuesday 6:30 pm Strength Yoga 600
Thursday 7:00 am Breath and Stretch 450
Saturday 9:00 am Beginners Basics 400
Sunday 8:00 am Slow Sunday 500

The page has a class booking form with the fields name, email, class and preferred date. The form sends the booking to the site's own API: POST /api/bookings stores it, and GET /api/bookings lists the stored bookings. The page shows the stored bookings under the form after a booking is made. The studio's contact email, shown as text, is bookings@stillpoint.example. Payment is made at the studio. No online payment is taken.

The teachers' names are not decided yet, and the studio has no phone number. Do not show teacher names or a phone number, and do not make any other detail up. Use only fake data in examples: the example booking is Test Person, test@stillpoint.example, Gentle Flow, next Monday.

The page must work on phones. The documents, the website and the backend must agree with each other.
