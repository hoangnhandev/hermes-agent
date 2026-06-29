# Automotive Conversion Tracking Setup

**Last Updated:** 2026-06-30
**Focus:** Test-drive booking, secondary conversions, offline import, landing page requirements

## Primary Conversion: Test-Drive Booking

### Conversion Action Setup

**Google Ads Conversion Action Settings:**

**Conversion Name:** `Test-Drive Booking - VinFast VF3`

**Conversion Category:** `Lead`

**Conversion Value:**
- **Value:** $100 (estimated lead value)
- **Always set value:** Yes
- **Rationale:** Test-drive = high intent, estimated $100 per lead (adjust based on actual sales data)

**Counting:**
- **Count:** `One` per click
- **Rationale:** Unique bookings only (don't count duplicate bookings)

**Click-Through Conversion Window:**
- **Window:** `30 days`
- **Rationale:** Automotive consideration cycle is weeks, not days

**Engagement-Through Conversion Window:**
- **Window:** `7 days`
- **Rationale:** Display/YouTube ads have longer consideration cycle

**Attribution Model:**
- **Model:** `Data-Driven` (preferred) or `Last Click` (fallback)
- **Requirement:** Data-driven requires 300+ conversions in 30 days (use Last Click initially)

### Google Tag Implementation

**Google Tag Manager Setup:**

**Step 1: Install Google Tag on All Pages**
```html
<!-- Google Tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-CONVERSION_ID"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'AW-CONVERSION_ID');
</script>
```

**Step 2: Add Conversion Event on Booking Confirmation Page**
```html
<!-- On /thank-you/booking-confirmed page -->
<script>
  gtag('event', 'conversion', {
    'send_to': 'AW-CONVERSION_ID/CONVERSION_LABEL',
    'value': 100.0,
    'currency': 'USD',
    'transaction_id': 'BOOKING-ID-12345'  // Optional: unique booking ID
  });
</script>
```

**Step 3: Add Enhanced Conversions (Optional but Recommended)**
```javascript
// Enhanced Conversions: User-provided data (email, phone)
gtag('set', 'user_data', {
  'email': 'user.email@example.com',
  'phone_number': '84xxxxxxxxx'  // Vietnam format: +84
});
```

### Landing Page Requirements

**Test-Drive Booking Landing Page:**

**Page Structure:**
```
/vf3-test-drive/
├── Hero Section (Value Proposition)
│   ├── Headline: "Đặt Lái Thử VF3 Miễn Phí"
│   ├── Subheadline: "Trải nghiệm xe điện mini giá rẻ nhất thị trường"
│   ├── CTA Button: "Đặt Lái Thử Ngay"
│   └── Trust Badges: "10 năm bảo hành", "Không cam kết"
│
├── Form Section (Single-Field for High Conversion)
│   ├── Phone Number Input (Primary)
│   ├── Name Input (Secondary)
│   ├── Preferred Date (Calendar)
│   ├── Dealer Location (Dropdown)
│   └── Submit Button: "Xác Nhận Đặt Lái Thử"
│
├── Social Proof Section
│   ├── "10,000+ Vietnamese đã lái thử"
│   ├── Customer Testimonials (3-5)
│   └── Media Mentions (Ogilvy Gold Award)
│
├── FAQ Section (Address Objections)
│   ├── "Có bắt buộc mua xe không?" → "Không, không cam kết"
│   ├── "Có mất phí không?" → "Hoàn toàn miễn phí"
│   └── "Cần giấy tờ gì?" → "Chỉ cần CMND/CCCD"
│
└── Footer Section
    ├── Dealer Contact Information
    ├── Privacy Policy Link
    └── Terms of Service Link
```

**Mobile Optimization (Critical - 70-80% Traffic):**
- **Form Fields:** Single-column layout, large inputs (16px+ font)
- **CTA Button:** Sticky at bottom, always visible
- **Load Speed:** <3 seconds on 4G Vietnam
- **Phone Number Input:** Auto-format (84 xxx xxx xxx)

**A/B Test Form Variations:**

**Variant A: Single-Field (Phone Only)**
- **Input:** Phone number only
- **Advantage:** Lowest friction, highest conversion rate
- **Follow-up:** Call user to collect details

**Variant B: Multi-Step (Progressive)**
- **Step 1:** Phone number
- **Step 2:** Name + preferred date
- **Step 3:** Dealer location
- **Advantage:** More data, better lead quality

**Variant C: Full Form (All Fields)**
- **Fields:** Phone, name, email, address, date, dealer
- **Advantage:** Complete data for CRM
- **Disadvantage:** Lower conversion rate

## Secondary Conversions (Track All)

### Conversion Hierarchy

| Conversion | Value | Counting | Priority | Tracking Method |
|------------|-------|----------|----------|-----------------|
| **Test-Drive Booking** | $100 | One | Primary (optimize for this) | Google Tag on thank-you page |
| **Dealer Inquiry (Form)** | $50 | One | Secondary | Google Tag on form submission |
| **Brochure Download** | $10 | One | Secondary | Google Tag on PDF download |
| **Phone Call (>=2min)** | $75 | One | Secondary | Google Forwarding Number |
| **Dealer Visit (Offline)** | $200 | One | Tertiary | Offline import (30-90 day lag) |
| **Vehicle Purchase (Offline)** | $25,000 | One | Ultimate | Offline import (30-90 day lag) |

### Brochure Download Tracking

**Setup:**

**Conversion Action Name:** `Brochure Download - VF3`

**Value:** $10 (lower intent than test-drive)

**Tracking Code:**
```html
<!-- On brochure download button click -->
<script>
  gtag('event', 'conversion', {
    'send_to': 'AW-CONVERSION_ID/BROCHURE_LABEL',
    'value': 10.0,
    'currency': 'USD'
  });
</script>
```

**Alternative: Link Click Tracking**
```html
<!-- On brochure link -->
<a href="/brochures/vf3.pdf"
   onclick="gtag('event', 'conversion', {
     'send_to': 'AW-CONVERSION_ID/BROCHURE_LABEL',
     'value': 10.0,
     'currency': 'USD'
   })">
  Download VF3 Brochure
</a>
```

### Phone Call Tracking

**Google Forwarding Number Setup:**

**Step 1: Enable Call Extensions**
- Campaign → Settings → Extensions → Call Extensions
- Set phone number to Google forwarding number
- Set business hours (9AM-6PM Vietnam time)

**Step 2: Configure Call Reporting**
- **Call Duration:** Count calls >60 seconds as conversions
- **Call Outcome:** Record "Connected" vs. "Not Connected"
- **Caller Area:** Track geographic location of callers

**Step 3: Assign Conversion Value**
- **Value:** $75 per qualified call (>60 seconds)
- **Rationale:** Phone call = high intent, but lower than test-drive booking

**Step 4: Feed into Smart Bidding**
- Ensure "Include in Conversions" = Yes
- tCPA/tROAS will optimize for phone calls + test-drive bookings

### Dealer Inquiry Form Tracking

**Setup:**

**Conversion Action Name:** `Dealer Inquiry - Contact Form`

**Value:** $50 (medium intent)

**Tracking Code:**
```html
<!-- On dealer contact form submission -->
<script>
  gtag('event', 'conversion', {
    'send_to': 'AW-CONVERSION_ID/CONTACT_LABEL',
    'value': 50.0,
    'currency': 'USD'
  });
</script>
```

**Landing Page:** `/contact-dealer/` (separate from test-drive booking)

**Form Fields:**
- Name, phone, email, preferred dealer, inquiry type

## Offline Conversion Import (Long-Term ROI)

### Why Offline Import Matters

**The Problem:**
- Google Ads optimizes for **last-click** (test-drive booking)
- But business goal is **vehicle sale** (30-90 days later)
- Without offline import, Google doesn't know true ROI

**The Solution:**
- **Offline Conversion Import:** Feed dealer CRM data back to Google Ads
- **Impact:** tCPA/tROAS optimizes for **sales**, not just test-drives
- **Result:** Higher ROI, better budget allocation

### Setup Process

**Step 1: Define Offline Conversions**

**Conversion 1: Dealer Visit**
- **Name:** `Dealer Visit - CRM Import`
- **Value:** $200 (high intent, but not yet purchased)
- **Lag Period:** 30 days (average time from booking to visit)
- **Import Frequency:** Weekly

**Conversion 2: Vehicle Purchase**
- **Name:** `Vehicle Purchase - CRM Import`
- **Value:** $25,000 (actual vehicle revenue)
- **Lag Period:** 60-90 days (average time from visit to purchase)
- **Import Frequency:** Monthly

**Step 2: Collect Data from CRM**

**Required Data Fields:**
| Field | Description | Example |
|-------|-------------|---------|
| **Google Click ID** | GCLID from Google Ads | `AW-123456789.123456789.123456789` |
| **Conversion Name** | Offline conversion action | `Vehicle Purchase - CRM Import` |
| **Conversion Time** | When purchase occurred | `2024-03-15 08:00:00` |
| **Conversion Value** | Revenue amount | `25000000` (VND) |

**GCLID Capture (Critical):**
- Capture GCLID on landing page (URL parameter: `?gclid=xxx`)
- Store GCLID in CRM with lead record
- Pass GCLID back to Google Ads when purchase occurs

**GCLID Capture Code:**
```javascript
// On landing page load
const urlParams = new URLSearchParams(window.location.search);
const gclid = urlParams.get('gclid');

// Store GCLID in hidden form field
document.getElementById('gclid-field').value = gclid;

// Or store in cookie/localStorage
localStorage.setItem('gclid', gclid);
```

**Step 3: Upload to Google Ads**

**Method A: Manual CSV Upload (Small Scale)**
```csv
Google Click ID,Conversion Name,Conversion Time,Conversion Value
AW-123456789.123456789.123456789,Vehicle Purchase - CRM Import,2024-03-15 08:00:00,25000000
AW-987654321.987654321.987654321,Dealer Visit - CRM Import,2024-03-10 14:30:00,200
```

**Upload Location:**
Tools → Conversions → Upload → Offline Conversions

**Method B: Automated Upload (Large Scale)**
- Use Google Ads API (offline_user_data_job service)
- Schedule daily/weekly automated uploads
- Integrate CRM → Google Ads API pipeline

**Step 4: Configure Import Settings**

**Offline Conversion Settings:**
- **Lag Duration:** 90 days (average consideration cycle)
- **Attribution Model:** Data-Driven (preferred) or Last Click
- **Import Frequency:** Daily (automated) or Weekly (manual)

### Offline Import Impact

**Before Offline Import:**
- Google optimizes for test-drive bookings ($100 value)
- Campaigns with high test-drive volume win
- Low test-drive cost = "good campaign" (even if no sales)

**After Offline Import:**
- Google optimizes for vehicle purchases ($25,000 value)
- Campaigns with high sales conversion win
- High sales ROI = "good campaign" (true business value)

**Expected Results:**
- **Budget Shift:** Budget moves toward high-sales campaigns
- **CPC Increase:** High-sales campaigns may have higher CPC (worth it)
- **ROI Improvement:** Overall account ROI increases by 15-30%

## Landing Page Optimization

### Page Speed Requirements

**Core Web Vitals (Google Ranking Factors):**

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| **LCP (Largest Contentful Paint)** | <2.5s | 2.5-4s | >4s |
| **FID (First Input Delay)** | <100ms | 100-300ms | >300ms |
| **CLS (Cumulative Layout Shift)** | <0.1 | 0.1-0.25 | >0.25 |

**Vietnam Mobile Network Speed (4G):**
- Average speed: 20-30 Mbps
- Target load time: <3 seconds on 4G
- Test with: PageSpeed Insights, Lighthouse

**Optimization Tips:**
- Compress images (WebP format, 80% quality)
- Minify CSS/JS
- Enable browser caching
- Use CDN (Cloudflare recommended)
- Lazy load below-fold content

### Mobile-First Design (Critical)

**Vietnam Device Split:**
- Mobile: 70-80% of traffic
- Desktop: 20-30% of traffic

**Mobile Best Practices:**
- **Font Size:** 16px minimum (readable without zoom)
- **Touch Targets:** 48x48px minimum (easy to tap)
- **Form Layout:** Single-column (stacked vertically)
- **CTA Button:** Sticky at bottom (always visible)
- **Phone Input:** Auto-format (84 xxx xxx xxx)

**Mobile Form Example:**
```html
<form id="test-drive-form">
  <!-- Single field for highest conversion -->
  <input type="tel" 
         id="phone" 
         placeholder="Số điện thoại (84 xxx xxx xxx)"
         pattern="[0-9]{10,11}"
         required>
  
  <button type="submit">
    Đặt Lái Thử Ngay
  </button>
</form>
```

### Conversion Rate Optimization (CRO)

**Industry Benchmarks:**
- **Automotive Landing Page CVR:** 7-10% (test-drive booking)
- **Top Performers:** 15-20% (optimized landing pages)

**CRO Best Practices:**

**1. Trust Signals (Above Fold)**
- "10,000+ Vietnamese đã lái thử"
- "Ogilvy Gold Award Winner"
- "10 năm bảo hành chính hãng"
- "Không cam kết mua xe"

**2. Value Proposition (Clear, Specific)**
- "280km cho mỗi lần sạc" (not "long range")
- "Chỉ từ 240 triệu VNĐ" (specific price)
- "500+ trạm sạc toàn quốc" (quantified infrastructure)

**3. Objection Handling (FAQ Section)**
- "Có bắt buộc mua không?" → "Không"
- "Có mất phí không?" → "Miễn phí 100%"
- "Cần giấy tờ gì?" → "Chỉ cần CMND"

**4. Social Proof (Testimonials)**
- Customer photos (real people, not stock)
- Video testimonials (Vietnamese language)
- Before/after stories (from gas car to EV)

**5. Urgency (Optional, Use Sparingly)**
- "Đặt hôm nay, lái thử trong 48h"
- "Chỉ còn 5 slot tuần này" (if true)

## Conversion Tracking Setup Checklist

### Pre-Launch Checklist

**Week 1: Technical Setup**
- [ ] Install Google Tag on all pages
- [ ] Create conversion actions (test-drive, brochure, call)
- [ ] Set up Google forwarding number (call extensions)
- [ ] Capture GCLID on landing pages (store in CRM)

**Week 2: Landing Page Optimization**
- [ ] Optimize page speed (<3s on 4G)
- [ ] Mobile-first design (test on 3-4 devices)
- [ ] Single-field form vs. multi-step (A/B test)
- [ ] Trust signals + social proof added

**Week 3: CRM Integration**
- [ ] Capture GCLID in CRM system
- [ ] Map CRM fields (booking date → visit date → purchase date)
- [ ] Set up offline import process (manual or automated)
- [ ] Test import with sample data

**Week 4: Testing + Launch**
- [ ] Test conversion tracking (submit test form)
- [ ] Verify conversion appears in Google Ads (within 24 hours)
- [ ] Test call tracking (call forwarding number)
- [ ] Test offline import (upload CSV with GCLID)

### Post-Launch Monitoring

**Daily Checks (First 2 Weeks):**
- [ ] Conversion tracking working (conversions appearing)
- [ ] No duplicate conversions
- [ ] Conversion value accurate ($100 per test-drive)
- [ ] GCLID capturing properly

**Weekly Checks:**
- [ ] Conversion rate by campaign (aim for 7-10%)
- [ ] Cost per conversion by campaign (aim for <$50)
- [ ] Mobile vs. desktop conversion rates
- [ ] Landing page load times (PageSpeed Insights)

**Monthly Checks:**
- [ ] Offline import data quality (GCLID match rate)
- [ ] Lag time analysis (booking → visit → purchase)
- [ ] Conversion value accuracy (actual revenue vs. $25,000 estimate)
- [ ) Smart bidding performance (tCPA vs. manual CPC)

## Troubleshooting

### Common Issues + Solutions

**Issue 1: No Conversions Showing**

**Possible Causes:**
- Google Tag not firing (check with Google Tag Assistant)
- Conversion tracking not installed on thank-you page
- Conversion action not linked to campaign
- Testing mode (conversion not counted)

**Solutions:**
- Verify Google Tag with Tag Assistant browser extension
- Check thank-you page source code for gtag event
- Ensure conversion action status = "Active"
- Turn off test mode after setup

**Issue 2: Duplicate Conversions**

**Possible Causes:**
- User clicks "Submit" button multiple times
- Conversion tag firing on multiple page views
- Thank-you page accessible without form submission

**Solutions:**
- Disable submit button after first click
- Fire conversion tag only on first thank-you page load
- Add form submission validation (server-side)

**Issue 3: Low Conversion Rate (<5%)**

**Possible Causes:**
- Landing page load time too slow (>5 seconds)
- Form too long (too many fields)
- CTA button not prominent enough
- No trust signals or social proof
- Wrong traffic (low-intent keywords)

**Solutions:**
- Optimize page speed (compress images, minify CSS/JS)
- Reduce form fields (single-field phone number)
- Make CTA button larger, higher contrast color
- Add testimonials, reviews, awards
- Check keyword targeting (exclude low-intent terms)

**Issue 4: Offline Import GCLID Not Matching**

**Possible Causes:**
- GCLID not captured on landing page
- GCLID stored incorrectly in CRM
- GCLID expired (90-day window)
- CRM export format incorrect

**Solutions:**
- Verify GCLID capture code on landing page
- Check CRM field mapping (GCLID field exists)
- Upload offline conversions within 90 days of click
- Use correct CSV format (Google Click ID, Conversion Name, Time, Value)

## Data Sources

- [Google Ads Help: Conversion Tracking Setup](https://support.google.com/google-ads/answer/1722054) - Official setup guide
- [Google Ads Help: Offline Conversions](https://support.google.com/google-ads/answer/6035983) - Offline import guide
- [DealerSmart: Test Drive Booking](https://www.dealersmart.com/insights/google-ads-for-dealers-turn-high-intent-searches-into-booked-test-drives) - Conversion tracking
- [LeadsBridge: Google Ads for Car Dealerships](https://leadsbridge.com/blog/google-ads-for-car-dealerships/) - CRM integration

---

*Note: Conversion tracking is the foundation of smart bidding. Without accurate tracking, automated bidding wastes budget. Test tracking thoroughly before scaling budget. Offline import is critical for true ROI optimization (30-90 day lag for automotive sales).*
