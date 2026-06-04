# Local Digest for SRC-0001-CHUNK-0001

## Big Picture

This source chunk provides a comprehensive overview of inflation, defining it as a generalized increase in the average price level of goods and services. It details how this phenomenon is measured (using the Consumer Price Index or IPC), explores various types of price changes (hyperinflation, deflation, disinflation), analyzes the sources that drive inflation (demand, cost, wages, monetary), discusses its economic consequences, and introduces methods for calculating both the CPI and the rate of inflation.

## Key Ideas

*   **Measurement:** The primary tool for measuring average price increases is the Consumer Price Index (IPC).
*   **Inflation Dynamics:** Inflation can be driven by an excess of demand over supply (demand-pull) or by rising costs of inputs (cost-push), such as raw materials or wages.
*   **Price Change Nuances:** It is crucial to distinguish between **Deflation** (generalized, prolonged price *decrease*) and **Disinflation** (a *slowing down* of the rate of price increase).
*   **Real vs. Nominal Values:** Inflation necessitates adjusting prices using inflation indices (like IPC) to determine the true purchasing power or value over time.
*   **Monetary Policy:** Central banks (like the Bank of Canada) manage monetary policy by setting an inflation target to maintain stable economic confidence and support growth.

## Definitions

| Term | Definition / Description | Source Page(s) |
| :--- | :--- | :--- |
| **Inflation** | A generalized increase in the average level of prices of goods and services within an economy over a given period. | 2 |
| **Consumer Price Index (IPC)** | The index used to measure the average price level of goods and services for consumers. In Canada, it is calculated using a basket containing over 600 items grouped into 8 categories. | 2, 3 |
| **Inflation Target** | The stable, low, and predictable inflation rate that central banks aim to maintain (e.g., the Bank of Canada's target of 2% in Canada). | 5 |
| **Hyper-inflation** | A severe episode where the general price level increases by more than 50% per month, or more than 1000% per year. | 7 |
| **Deflation** | In a macroeconomic context, it implies a generalized and prolonged *decrease* in the prices of goods and services. | 7 |
| **Disinflation** | Defined as a deceleration (slowing down) of the rate of price increase (i.e., prices continue to rise, but at a slower pace). | 7 |
| **Inflation by Costs / Imported Inflation** | Inflation caused by increases in the prices of imported raw materials, intermediate goods, or equipment, which are passed on to the final consumer price. | 9 |
| **Inflation by Wages** | Occurs when wage increases exceed productivity growth, leading companies to raise selling prices to maintain profit maximization. | 9 |
| **Monetary Inflation** | Price fluctuations caused by variations in the money supply (currency, deposits, treasury bonds). | 9 |
| **Real Value vs. Nominal Value** | *Nominal value* is the price/amount measured at a specific time. *Real value* adjusts for inflation to show what that amount could actually purchase over time. | 15 |

## Formulas / Rules / Methods

### 1. Consumer Price Index (IPC) Calculation
The IPC measures the cost of a fixed basket of goods in different years relative to a base year.

*   **General Formula:** $\text{IPC}_{\text{année } t} = \frac{\text{coût dépenses année } t}{\text{coût dépenses année de base}} \times 100$
*   **Base Year Rule:** The IPC for the base year is set to 100.

### 2. Inflation Rate (Taux d’inflation, TI) Calculation

The inflation rate measures the relative change in the IPC over a period.

*   **Two Consecutive Periods ($t-1$ and $t$):**
    $$\text{TI} = \frac{\text{IPC}_t - \text{IPC}_{t-1}}{\text{IPC}_{t-1}} \times 100$$
*   **Over $n$ Variations (General Formula):**
    $$\text{TI} = \left( \frac{\text{IPC}_{\text{période finale}}}{\text{IPC}_{\text{période initiale}}} - 1 \right) \times n \times 100$$

### 3. Using the Deflator (Alternative TI Calculation)
The inflation rate can also be calculated using the deflator index:

*   **Two Consecutive Periods:** $\text{TI} = \frac{\text{Déflatteur}_t - \text{Déflatteur}_{t-1}}{\text{Déflatteur}_{t-1}} \times 100$
*   **Over $n$ Variations (General Formula):** $$\text{TIAM} = \left( \frac{\text{Déflatteur}_{\text{période finale}}}{\text{Déflatteur}_{\text{période initiale}}} - 1 \right) \times n \times 100$$

### 4. Fisher Equation (Interest Rates)
This equation relates the three types of interest rates:

$$\text{Taux d'intérêt réel} = \text{Taux d'intérêt nominal} - \text{Taux d'inflation}$$

## Step-by-Step Procedures

**A. Calculating IPC:**
1.  Determine the fixed basket of goods (quantities).
2.  Calculate the total cost of this basket in Year 1 ($\text{Coût}_{\text{année } 1}$).
3.  Set $\text{IPC}_{\text{année de base}} = 100$.
4.  For subsequent years, calculate the ratio: $\frac{\text{Coût dépenses année } t}{\text{Coût dépenses année de base}}$.

**B. Calculating Inflation Rate (TI):**
1.  Identify the IPC for the starting period ($\text{IPC}_{\text{initial}}$) and the ending period ($\text{IPC}_{\text{final}}$).
2.  Use the general formula: $\left( \frac{\text{IPC}_{\text{final}}}{\text{IPC}_{\text{initial}}} - 1 \right) \times n \times 100$.

**C. Adjusting for Inflation (Real Value):**
To find the equivalent price of a good purchased in Year A, when measured by the prices of Year B:
$$\text{Prix en année B} = \text{Prix initial} \times \left( \frac{\text{IPC}_{\text{année B}}}{\text{IPC}_{\text{année A}}} \right)$$

## Worked Examples from the Source

**1. The Uncle's Beer Story (Page 16-17):**
*   **Scenario:** Price of beer in 1975 was \$10.00; price in 1995 was \$24.00. $\text{IPC}_{1975} = 34.5$; $\text{IPC}_{1995} = 104.2$.
*   **Goal (a): Equivalent 1975 price in 1995 dollars:**
    $$\$10.00 \times \left( \frac{104.2}{34.5} \right) = \$30.20$$
*   **Goal (b): Equivalent 1995 price in 1975 dollars:**
    $$\$24.00 \times \left( \frac{34.5}{104.2} \right) = \$7.95$$
*   **Conclusion:** Both methods show that, when adjusted for inflation, the beer was more expensive in 1975 than it was in 1995.

**2. Application 1 (Page 20):**
*   **Basket:** 2 units of A and 3 units of B. Base Year = Year 1.
*   **IPC Calculation:**
    *   $\text{IPC}_{\text{Year } 1} = 100$ (Base)
    *   $\text{IPC}_{\text{Year } 2} = \frac{(2 \times 4 + 3 \times 2)}{(2 \times 2 + 3 \times 1)} \times 100 = \frac{14}{7} \times 100 = 200$
    *   $\text{IPC}_{\text{Year } 3} = \frac{(6 \times 2 + 3 \times 4)}{(2 \times 2 + 3 \times 1)} \times 100 = \frac{24}{7} \times 100 = 342$
*   **Inflation Rate (TI):**
    *   Year 1 to Year 2: $\left( \frac{200 - 100}{100} \right) \times 100 = 100\%$
    *   Year 1 to Year 3: $\left( \frac{342}{100} - 1 \right) \times 2 \times 100 = 84.93\%$

## New Practice Examples

**Conceptual Example (Inflation Sources):**
If a country experiences a sudden, sharp increase in the global price of oil (a raw material), which source of inflation is most likely to be responsible?
*   *Answer:* Inflation by costs or imported inflation. The increased cost of oil raises production costs across many industries, which are then passed on to consumers.

**Conceptual