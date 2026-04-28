The system focuses on identifying and mitigating the following **three core anomalies**:

### 1. The "Silent" Memory Leak (Sustained Trend)
This is a primary focus of your AIOps system[cite: 46, 47]. [cite_start]Unlike Kubernetes, which waits for a crash, your system identifies the "Intelligence Gap" by looking at behavioral patterns[cite: 39, 42].
* [cite_start]**The Anomaly:** A slow, steady creep in CPU or memory utilization over time[cite: 47, 49].
* [cite_start]**Detection:** The system uses **Trend Analysis** to identify a statistical upward trajectory (e.g., increasing every minute for 5+ minutes)[cite: 35, 36, 49].
* [cite_start]**Mitigation:** The engine triggers a graceful restart or "Scale Out" event during a low-traffic window *before* the service actually dips[cite: 50].

### 2. Performance Degradation (Plateaued Crisis)
Standard monitoring might ignore a high but "flat" metric if it doesn't cross a 90% "panic" threshold. [cite_start]Your MVP identifies **Sustained Anomalies** that indicate genuine degradation[cite: 17, 33].
* [cite_start]**The Anomaly:** A resource (like your m7.large) hitting a high plateau (e.g., 60-70%) and staying there for a prolonged period, indicating a stuck process or "zombie" task[cite: 14, 17].
* [cite_start]**Detection:** Evaluates **Duration** (Temporal analysis) to ensure the anomaly is sustained (e.g., >3 minutes)[cite: 35].
* [cite_start]**Mitigation:** Executes a **Restart** or **Reboot** to clear the stuck state and restore performance[cite: 36].

### 3. Operational "Flapping" (Runaway Automation)
[cite_start]One of the most dangerous anomalies in automation is the "feedback loop" where a system keeps trying to fix a problem that isn't yet fixed[cite: 12].
* [cite_start]**The Anomaly:** Rapid, repeated automated actions (rebooting every 2 minutes) caused by a system that is "context-blind" to its own recent history[cite: 11, 12].
* [cite_start]**Detection:** The Brain performs a **History & Cooldown Validation** by checking the DynamoDB state store for recent remediation entries[cite: 19, 35, 36].
* [cite_start]**Mitigation:** The system hits an **Action Quota** or **Cooldown** state and chooses to **IGNORE** further actions, preventing unnecessary costs or further instability[cite: 19, 36, 53].

---
