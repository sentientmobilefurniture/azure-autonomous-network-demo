# Recommendation Model Bias — Investigation Runbook

## Trigger Conditions
- MODEL_BIAS_DETECTED alert from any Campaign
- ReturnRatePct > 10% on any CustomerSegment
- AvgOrderValueUSD > $500 for SEG-NEW, SEG-CASUAL, or SEG-WINBACK

## Investigation Flow

### Step 1: Identify Affected Segments
Query which segments show anomalous return rates:
```
g.V().hasLabel('CustomerSegment').valueMap(true)
```
Compare current ReturnRatePct against baselines (normal: 1–3%).

### Step 2: Trace Campaign → Product → Segment Relationships
Find which campaigns are promoting products to the wrong segments:
```
g.V().has('Campaign','CampaignId','CAMP-NEWUSER-Q1')
  .out('targets').valueMap(true)
```
Then check what products those campaigns promote:
```
g.V().has('Campaign','CampaignId','CAMP-NEWUSER-Q1')
  .out('promotes').valueMap(true)
```

### Step 3: Check Product-Segment Price Alignment
For each promoted product, verify the price matches the segment's spending range:
- SEG-NEW: MaxSpendUSD = $199
- SEG-CASUAL: MaxSpendUSD = $1,999
- SEG-VIP: MaxSpendUSD = unlimited

Products priced above the segment's MaxSpendUSD indicate a recommendation bias.

### Step 4: Review Purchase History for Returns
```
g.V().has('Customer','CustomerId','CUST-008')
  .outE('purchased').has('returned','Y')
  .inV().valueMap(true)
```

## Remediation

1. Roll back recommendation model to previous version
2. Disable affected campaigns temporarily
3. Issue apology credits to affected customers
4. Retrain model with price-sensitivity features
