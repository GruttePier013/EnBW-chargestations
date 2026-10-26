# Changelog

## 0.5.0
- Nieuwe afbeeldingen: integratielogo (ook in de README en `brand/` voor HACS/HA) en kaartmarkers *beschikbaar* en *niet beschikbaar*, plus een grijze marker met vraagteken voor onbekend/verouderd. De marker *gedeeltelijk* is ongewijzigd.
- Gegevens ouder dan 1 dag: visuele sensor toont ⚫, de laadpaal-op-kaart toont de onbekend-marker en geen status.
- Nieuwe actie `enbw_laadpalen.refresh_all` en knop *Alle laadpalen vernieuwen* (apparaat *EnBW Laadpalen*).
- Statussen als INOPERATIVE, FAULTED, BLOCKED, UNAVAILABLE e.d. tellen nu als *buiten werking*.

## 0.4.3
- **Bugfix:** de backoff gebruikte de attribuutnaam `_retry_after`, die ook door `DataUpdateCoordinator` wordt gebruikt en bij init wordt overschreven. Hernoemd naar `_backoff_until`.
- Opstart: eerste verversing maximaal 5 laadpalen tegelijk.
- Uitladen ruimt ook de herstelmeldingen per laadpaal op.
- *Laadpunt*-icoon bij onbekende status is nu een vraagteken.
- Typering opgeschoond (mypy zonder fouten), 3 extra regressietests.

## 0.4.2
- Zoekstap: het dubbele paar GPS-velden is weg. Alleen het paar van de kaartkiezer blijft (naast elkaar, live gekoppeld aan de pin). Uitleg bovenaan ingekort.

## 0.4.1
- *Laadpaal op kaart*: de status in het meer-info-venster (klik op het icoon op de kaart) toont nu `2/4 beschikbaar` in plaats van de zonenaam; extra gegevens staan in de attributen.

## 0.4.0
- **Foutbeveiliging:** per laadpaal backoff en pauze na X fouten (sensor *Gepauzeerd*, melding in *Herstellen*), en een circuit breaker voor de hele API (5xx/429/time-outs, respecteert `Retry-After`). Handmatig vernieuwen omzeilt de pauze en hervat.
- **Spreiding:** automatische aanroepen met N seconden tussenruimte (standaard 3 s).
- **Event** `enbw_laadpalen_charge_point_available` + event-entiteit als een laadpunt vrijkomt terwijl iemand in de zone is.
- **Sensor** *Afstand tot dichtstbijzijnde persoon*; **slimmer verversen**: schakelaar *Alleen vernieuwen bij naderen* (standaard aan, ook in de standaardwaarden).
- **Diagnostics-download** met het ruwe EnBW-antwoord.
- Openingstijden met Nederlandse dagnamen (Ma-Vr).
- **Recorder ontlast:** attributen van alle entiteiten worden niet meer in de database bewaard; statistieken alleen voor *Beschikbare laadpunten*.
- **Code in het Engels:** attribuutnamen zijn Engels geworden (breaking: `laadpunten` → `charge_points`, `vrij` → `available`, `bezet` → `occupied`, `bijgewerkt` → `updated`, enz.) en interne statussen (`available`, `occupied`, `out_of_service`, `unknown`).

## 0.3.4
- Resultatenlijst: rij 1 = adres; rij 2 = `2/2 ⚡ beschikbaar, 17kW 🗼, 2925161 📍, 140m ↘ ZO` (status nu in de helpertekst, vertaald NL/EN); geen icoon meer voor de fun fact.
- Voorgestelde apparaatnaam (en rij 1) zonder postcode: `Voorbeeldlaan 14, Voorbeeldstad, NL`.

## 0.3.3
- Fun fact zonder vergelijking: alleen het totale laadvermogen in de zone.
- Plaatsnaam zoeken: een kale plaatsnaam zoekt eerst alleen woonplaatsen (centrum van de plaats, niet het middelpunt van de gemeente); met huisnummer of komma blijft het zoeken in alle typen.
- Resultatenlijst: per laadpaal een eigen veld met checkbox + `2/2 ⚡ - Naam` en daaronder, links uitgelijnd, `17kW 🗼, 2925161 📍, 140m ↘ ZO` (helpertekst in plaats van een tweede regel in het label).

## 0.3.2
- Resultatenstap: kop `6 Laadpalen gevonden.` komt nu uit de vertalingen (taal van je gebruikersprofiel) in plaats van uit de systeemtaal; apart enkelvoud (`1 Laadpaal gevonden.`).
- Subtitel met fun fact: totaal aan laadvermogen in de zone (som van alle laadpunten) en wat dat betekent in waterkokers.

## 0.3.1
- Zoekstap: invoerveld *Plaatsnaam of adres* boven de kaart; na *Verzenden* springt de pin (en de GPS-velden) naar die plek. PDOK-zoekresultaat: eerste (meest relevante) treffer.
- Resultatenlijst: nieuwe opmaak `2/2 ⚡ - Naam` met op de regel eronder `17kW 🗼, 2925161 📍, 140m ↘ ZO`.

## 0.3.0
- Configflow: nieuw scherm *Standaardwaarden* direct na de API-sleutel (vernieuwingsfrequentie, zone radius, vernieuwen in zone, frequentie en maximale tijdsperiode in de zone).
- Configureren: *API-sleutel* is uit het menu en zit nu in *Instellingen*; daar staan ook dezelfde standaardwaarden met het vinkje *Toepassen op bestaande laadpalen* (standaard uit).
- Nieuwe laadpalen starten met deze standaardwaarden; bestaande houden hun eigen keuze tenzij het vinkje aan staat.

## 0.2.0
- Verversen in de zone per bezoek: *Vernieuwen in zone stoppen na*, afkoeltijd na vertrek (opties), standaard 5 min / 30 min / 1000 m.
- *Beschikbaarheid visueel* toont één icoon per laadpunt (`🅿️/⛔`).
- Kaartafbeeldingen: alles beschikbaar (groen vinkje), deels (vinkje + kruis), niets (rood kruis). Integratie-icoon met witte achtergrond en afgeronde hoeken.
- Selectielijst: checkbox vóór elke laadpaal zonder nummering; 📍 code en details op een nieuwe regel.
- Fix: beschrijving in de selectiestap viel terug op Engels doordat de placeholders in NL en EN verschilden.

## 0.1.3
- Nieuw: *Vernieuwingsfrequentie in zone* (bij binnenkomst 1x, elke 2/10/15 min zolang iemand in de zone is); *Vernieuwen in zone* is de hoofdschakelaar. *Standaard vernieuwingsfrequentie* heet nu *Vernieuwingsfrequentie*.

## 0.1.2
- EnBW-logo's: integratie-icoon (`brand/`, HA 2026.3+) en kaartafbeeldingen voor de laadpaal (blauw = beschikbaar, rood kruis = niet beschikbaar).

## 0.1.1
- Hernoemd naar EnBW Laadpalen; coördinaatvelden onder de kaart (pin en velden synchroon bij verzenden); selectielijst met checkbox vóór elke genummerde regel; `Type 2` i.p.v. `Typ 2`; status `1/2 beschikbaar`; Personen nabij toont namen (binary_sensor Persoon nabij verwijderd); Beschikbare laadpunten; Beschikbaarheid visueel (🅿️ ⛔ ⚫); binary_sensor per laadpunt (Bezet/Vrij/Onbekend); diagnosesensor Locatiecode.

## 0.1.0
- Eerste versie: API-sleutel, zoeken via kaartzone/adres/coördinaten of stationsnummer, connector- en vermogensfilter, verversschema per station, nabijheid, device tracker, NL+EN vertalingen, tests en CI.
