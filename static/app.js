(() => {
  const DEFAULT_HOURLY_RATE_PENCE = 2500;
  let hourlyRatePence = DEFAULT_HOURLY_RATE_PENCE;

  function lineCostPence(hours, ratePence = hourlyRatePence) {
    const h = Number(hours);
    const r = Number(ratePence);
    if (!Number.isFinite(h) || h < 0 || !Number.isFinite(r) || r < 0) {
      return 0;
    }
    return Math.round(h * r);
  }

  function totalPence(tasks, ratePence = hourlyRatePence) {
    if (!Array.isArray(tasks)) {
      return 0;
    }
    let sum = 0;
    for (const task of tasks) {
      if (task && task.enabled !== false) {
        sum += lineCostPence(task.hours, ratePence);
      }
    }
    return sum;
  }

  function formatPenceGbp(pence) {
    const safe = Number.isFinite(pence) && pence >= 0 ? Math.round(pence) : 0;
    return `£${(safe / 100).toFixed(2)}`;
  }

  window.lineCostPence = lineCostPence;
  window.totalPence = totalPence;

  const form = document.getElementById("adjust-form");
  const tbody = document.getElementById("quote-tbody");
  const errorEl = document.getElementById("error-msg");
  const bookingMsgEl = document.getElementById("booking-msg");
  const totalHoursEl = document.getElementById("total-hours");
  const totalGbpEl = document.getElementById("total-gbp");
  const hourlyRateEl = document.getElementById("hourly-rate");
  const demoBadgeEl = document.getElementById("demo-badge");
  const photoInput = document.getElementById("photo-input");
  const sampleBtn = document.getElementById("sample-btn");
  const analyseBtn = document.getElementById("analyse-btn");
  const bookBtn = document.getElementById("book-btn");
  const weekCalendarEl = document.getElementById("week-calendar");
  const quoteMessageEl = document.getElementById("quote-message");
  const copyBtn = document.getElementById("copy-btn");
  const quoteSubtitleEl = document.getElementById("quote-subtitle");
  const photoFilenameLabel = document.getElementById("photo-filename-label");
  const photoStatusBadge = document.getElementById("photo-status-badge");
  const sampleGardenSvg = document.getElementById("sample-garden-svg");
  const uploadedPhotoImg = document.getElementById("uploaded-photo-img");

  let useSample = false;
  let selectedFile = null;
  let isBookingInFlight = false;
  let isBookedForCurrentQuote = false;
  let currentBookedSlot = null;
  let currentWeek = [];
  let copyResetTimer = null;
  let hasHoursValidationError = false;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setErrorMessage(msg) {
    if (!errorEl) return;
    errorEl.textContent = msg || "";
  }

  function setHourlyRatePence(pence) {
    const parsed = Number(pence);
    if (Number.isFinite(parsed) && parsed > 0) {
      hourlyRatePence = Math.round(parsed);
    }
    if (hourlyRateEl) {
      hourlyRateEl.textContent = formatPenceGbp(hourlyRatePence);
    }
  }

  function updateDemoBadge(mode) {
    if (!demoBadgeEl) return;
    if (mode === "live") {
      demoBadgeEl.hidden = true;
    } else if (mode === "demo") {
      demoBadgeEl.hidden = false;
      demoBadgeEl.textContent = "DEMO MODE";
    }
  }

  function validateHourInput(hourInput) {
    if (!hourInput) {
      return { valid: true, hours: 0, error: null };
    }
    if (hourInput.validity && hourInput.validity.badInput) {
      return {
        valid: false,
        hours: 0,
        error: "Please enter a valid number of hours between 0 and 40.",
      };
    }
    const raw = String(hourInput.value ?? "").trim();
    if (raw === "") {
      return {
        valid: false,
        hours: 0,
        error: "Hours cannot be empty; enter a number between 0 and 40.",
      };
    }
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      return {
        valid: false,
        hours: 0,
        error: "Please enter a valid number of hours between 0 and 40.",
      };
    }
    if (parsed < 0) {
      return {
        valid: false,
        hours: 0,
        error: "Hours cannot be negative (minimum 0).",
      };
    }
    if (parsed > 40) {
      return {
        valid: false,
        hours: 0,
        error: "Hours cannot exceed 40 hours per task.",
      };
    }
    return { valid: true, hours: parsed, error: null };
  }

  function getRowState(row) {
    const taskId = row.dataset.taskId || "";
    const taskName = row.dataset.taskName || "";
    const initialHours = parseFloat(row.dataset.initialHours) || 0;
    const checkbox = row.querySelector('[data-testid="task-tick"]');
    const hourInput = row.querySelector('[data-testid="task-hours"]');
    const badgeEl = row.querySelector(`[data-task-badge="${taskId}"]`);
    const costCell = row.querySelector('[data-testid="task-cost"]');
    const checked = checkbox ? checkbox.checked : false;
    const validation = validateHourInput(hourInput);
    const hours = validation.valid ? validation.hours : 0;
    const costPence = checked ? lineCostPence(hours, hourlyRatePence) : 0;

    return {
      taskId,
      taskName,
      initialHours,
      checkbox,
      hourInput,
      badgeEl,
      costCell,
      checked,
      hours,
      costPence,
      valid: validation.valid,
      validationError: validation.error,
    };
  }

  function updateRowVisualState(row, item) {
    row.classList.toggle("row-disabled", !item.checked);
    if (item.hourInput) {
      item.hourInput.classList.toggle("input-invalid", !item.valid);
      item.hourInput.setAttribute("aria-invalid", item.valid ? "false" : "true");
    }
    if (!item.badgeEl) return;
    if (!item.checked) {
      item.badgeEl.innerHTML = '<span class="excluded-pill">Excluded</span>';
    } else if (item.valid && item.initialHours > 0 && Math.abs(item.hours - item.initialHours) >= 0.01) {
      const diff = item.hours - item.initialHours;
      const sign = diff > 0 ? "+" : "";
      item.badgeEl.innerHTML = `<span class="adjusted-pill">Adjusted (${sign}${diff.toFixed(2)}h)</span>`;
    } else {
      item.badgeEl.innerHTML = "";
    }
  }

  function getDayLabelForDate(dateStr) {
    const match = currentWeek.find((d) => d.date === dateStr);
    return match && match.label ? match.label : dateStr;
  }

  function updateQuoteMessage() {
    if (!quoteMessageEl) return;
    const rows = Array.from(tbody.querySelectorAll('tr[data-testid="task-row"]'));
    const taskRecords = [];
    const tickedLines = [];
    let totalHours = 0;

    for (const row of rows) {
      const item = getRowState(row);
      taskRecords.push({ hours: item.hours, enabled: item.checked });
      if (item.checked && item.hours > 0) {
        totalHours += item.hours;
        tickedLines.push(
          `• ${item.taskName}: ${item.hours.toFixed(2)} hrs — ${formatPenceGbp(item.costPence)}`
        );
      }
    }

    const quoteTotalPence = totalPence(taskRecords, hourlyRatePence);
    let bookingText = "Not yet booked";
    if (currentBookedSlot) {
      const dayLabel = currentBookedSlot.label || getDayLabelForDate(currentBookedSlot.date);
      bookingText = `${dayLabel} (${currentBookedSlot.date}), ${currentBookedSlot.start}–${currentBookedSlot.end}`;
    }

    const lines = [
      "TurfTruth Garden Quote — Mrs. Higgins (14 Oak Lane)",
      ...(tickedLines.length > 0 ? tickedLines : ["No tasks selected."]),
      `Total: ${formatPenceGbp(quoteTotalPence)} (${totalHours.toFixed(2)} hrs @ ${formatPenceGbp(hourlyRatePence)}/hr)`,
      `Booked slot: ${bookingText}`,
    ];
    quoteMessageEl.textContent = lines.join("\n");
  }

  function recalculateClientTotals() {
    const rows = Array.from(tbody.querySelectorAll('tr[data-testid="task-row"]'));
    let totalHours = 0;
    let anyChecked = false;
    let firstValidationError = null;
    const taskRecords = [];

    for (const row of rows) {
      const item = getRowState(row);
      updateRowVisualState(row, item);
      if (!item.valid && !firstValidationError) {
        firstValidationError = item.validationError;
      }
      taskRecords.push({ hours: item.hours, enabled: item.checked });
      if (item.checked) {
        anyChecked = true;
        totalHours += item.hours;
      }
      if (item.costCell) {
        item.costCell.textContent = formatPenceGbp(item.costPence);
      }
    }

    const quoteTotalPence = totalPence(taskRecords, hourlyRatePence);
    if (totalHoursEl) {
      totalHoursEl.textContent = totalHours.toFixed(2);
    }
    if (totalGbpEl) {
      totalGbpEl.textContent = formatPenceGbp(quoteTotalPence);
    }

    if (firstValidationError) {
      hasHoursValidationError = true;
      setErrorMessage(firstValidationError);
    } else if (hasHoursValidationError) {
      hasHoursValidationError = false;
      setErrorMessage("");
    }

    if (rows.length === 0) {
      bookBtn.disabled = true;
      if (!isBookedForCurrentQuote && bookingMsgEl) {
        bookingMsgEl.classList.remove("is-error");
        bookingMsgEl.textContent = "";
      }
    } else if (firstValidationError) {
      bookBtn.disabled = true;
    } else if (!anyChecked || totalHours <= 0) {
      bookBtn.disabled = true;
      if (!isBookedForCurrentQuote && bookingMsgEl) {
        bookingMsgEl.classList.add("is-error");
        bookingMsgEl.textContent = "Tick at least one task with hours > 0 to book a slot.";
      }
    } else if (!isBookedForCurrentQuote && !isBookingInFlight) {
      bookBtn.disabled = false;
      bookBtn.textContent = "Book next free slot";
      if (
        bookingMsgEl &&
        bookingMsgEl.textContent === "Tick at least one task with hours > 0 to book a slot."
      ) {
        bookingMsgEl.classList.remove("is-error");
        bookingMsgEl.textContent = "";
      }
    }

    updateQuoteMessage();
    return {
      totalHours,
      quoteTotalPence,
      anyChecked,
      hasValidationError: Boolean(firstValidationError),
    };
  }

  function renderTasks(tasks) {
    isBookedForCurrentQuote = false;
    currentBookedSlot = null;
    hasHoursValidationError = false;
    bookBtn.textContent = "Book next free slot";
    if (bookingMsgEl) {
      bookingMsgEl.classList.remove("is-error");
      bookingMsgEl.textContent = "";
    }

    if (!Array.isArray(tasks) || tasks.length === 0) {
      tbody.innerHTML = "";
      if (photoStatusBadge) {
        photoStatusBadge.textContent = "0 Tasks Loaded";
      }
      recalculateClientTotals();
      renderCalendar(currentWeek);
      return;
    }

    if (photoStatusBadge) {
      photoStatusBadge.textContent = `${tasks.length} Visual Tasks Detected`;
    }
    if (quoteSubtitleEl) {
      quoteSubtitleEl.innerHTML =
        'Active Quote — <span id="client-name-label">Mrs. Higgins — 14 Oak Lane</span>';
    }

    const rateDisplay = formatPenceGbp(hourlyRatePence);
    tbody.innerHTML = tasks
      .map((rawTask, idx) => {
        const id = rawTask.id || rawTask.task_id || `t${idx + 1}`;
        const name = rawTask.name || rawTask.task_name || `Task ${idx + 1}`;
        const hours = Number(rawTask.hours ?? rawTask.estimated_hours ?? 0);
        const evidence = rawTask.evidence || rawTask.visual_evidence || "";
        const enabled = rawTask.enabled !== false;
        const costStr = formatPenceGbp(enabled ? lineCostPence(hours, hourlyRatePence) : 0);
        const checkId = `task-check-${escapeHtml(id)}`;
        const hoursId = `task-hours-${escapeHtml(id)}`;

        return `
          <tr
            data-testid="task-row"
            data-task-id="${escapeHtml(id)}"
            data-task-name="${escapeHtml(name)}"
            data-initial-hours="${hours.toFixed(2)}"
            class="${enabled ? "" : "row-disabled"}"
          >
            <td>
              <label for="${checkId}" class="sr-only">Include ${escapeHtml(name)}</label>
              <input
                id="${checkId}"
                type="checkbox"
                ${enabled ? "checked" : ""}
                data-testid="task-tick"
                data-task-check="${escapeHtml(id)}"
                aria-label="Include ${escapeHtml(name)}"
              />
            </td>
            <td data-testid="task-name">
              <div class="task-name-cell">
                <span class="task-idx-badge">${idx + 1}</span>
                <span class="task-title-text">${escapeHtml(name)}</span>
              </div>
            </td>
            <td data-testid="task-evidence" class="evidence-cell">${escapeHtml(evidence)}</td>
            <td>
              <div class="hours-cell-wrap">
                <label for="${hoursId}" class="sr-only">Hours for ${escapeHtml(name)}</label>
                <input
                  id="${hoursId}"
                  type="number"
                  step="0.25"
                  min="0"
                  max="40"
                  name="hours-${escapeHtml(id)}"
                  value="${hours.toFixed(2)}"
                  data-testid="task-hours"
                  data-task-hours="${escapeHtml(id)}"
                  aria-label="Hours for ${escapeHtml(name)}"
                />
                <span data-task-badge="${escapeHtml(id)}"></span>
              </div>
            </td>
            <td>${rateDisplay}</td>
            <td data-testid="task-cost" class="line-total-cell" data-line-total="${escapeHtml(id)}">${costStr}</td>
          </tr>`;
      })
      .join("");

    recalculateClientTotals();
    renderCalendar(currentWeek);
  }

  function normalizeCalendarPayload(data) {
    if (!data) return [];
    if (Array.isArray(data.week)) {
      return data.week.map((day) => ({
        date: day.date,
        label: day.label || day.day_label || day.date,
        weather: day.weather || (day.rain ? "Rain forecast" : "Dry conditions"),
        rain: Boolean(day.rain ?? day.is_rain),
        bookings: Array.isArray(day.bookings)
          ? day.bookings.map((b) => ({
              start: b.start,
              end: b.end,
              title: b.title || "Garden booking",
              isNew: Boolean(b.isNew),
            }))
          : [],
      }));
    }
    if (Array.isArray(data.days)) {
      const slotsByDate = {};
      for (const s of data.slots || []) {
        if (!slotsByDate[s.date]) slotsByDate[s.date] = [];
        slotsByDate[s.date].push({
          start: s.start,
          end: s.end,
          title: s.title || "Garden booking",
          isNew: false,
        });
      }
      return data.days.map((day) => ({
        date: day.date,
        label: day.day_label || day.label || day.date,
        weather: day.weather || (day.is_rain ? "Rain forecast" : "Dry conditions"),
        rain: Boolean(day.is_rain ?? day.rain),
        bookings: slotsByDate[day.date] || [],
      }));
    }
    return [];
  }

  function renderCalendar(week) {
    if (!weekCalendarEl) return;
    currentWeek = Array.isArray(week) ? week : [];

    weekCalendarEl.innerHTML = currentWeek
      .map((day) => {
        const isRain = Boolean(day.rain);
        const bookings = Array.isArray(day.bookings) ? [...day.bookings] : [];

        if (
          currentBookedSlot &&
          currentBookedSlot.date === day.date &&
          !isRain
        ) {
          const existingIdx = bookings.findIndex(
            (b) => b.start === currentBookedSlot.start && b.end === currentBookedSlot.end
          );
          if (existingIdx >= 0) {
            bookings[existingIdx] = {
              ...bookings[existingIdx],
              isBookedSlot: true,
            };
          } else {
            bookings.push({
              start: currentBookedSlot.start,
              end: currentBookedSlot.end,
              title: "Confirmed TurfTruth Job",
              isBookedSlot: true,
            });
          }
        }

        bookings.sort((a, b) => String(a.start).localeCompare(String(b.start)));
        const hasNewBooking = bookings.some((b) => Boolean(b.isBookedSlot));
        const dayTestIdAttr = isRain ? ' data-testid="rain-day"' : "";
        const dayClass = `day-card${isRain ? " rain-day" : " dry-day"}${
          hasNewBooking ? " has-new-booking" : ""
        }`;
        const weatherBadge = isRain
          ? '<span class="rain-badge">🌧️ Rain — No outdoor work</span>'
          : '<span class="dry-badge">☀️ Dry — Weather-Safe</span>';

        const slotsHtml =
          bookings.length > 0
            ? bookings
                .map((b) => {
                  const isNew = Boolean(b.isBookedSlot);
                  const testId = isNew ? "booked-slot" : "existing-booking";
                  const cls = isNew
                    ? "slot-block booked-slot slot-new"
                    : "slot-block existing-booking";
                  const newTag = isNew
                    ? '<div class="slot-new-tag">✓ Booked Slot</div>'
                    : "";
                  return `<div class="${cls}" data-testid="${testId}" data-date="${escapeHtml(
                    day.date
                  )}" data-start="${escapeHtml(b.start)}" data-end="${escapeHtml(
                    b.end
                  )}">${newTag}<strong>${escapeHtml(b.start)}–${escapeHtml(
                    b.end
                  )}</strong><br/><span>${escapeHtml(b.title || "Booked Job")}</span></div>`;
                })
                .join("")
            : isRain
            ? ""
            : '<div class="slot-empty">Free 08:00–17:00</div>';

        return `
          <div class="${dayClass}"${dayTestIdAttr} data-date="${escapeHtml(
          day.date
        )}" data-is-rain="${isRain}">
            <div class="day-header">${escapeHtml(day.label)}</div>
            <div class="day-weather">${escapeHtml(day.weather || (isRain ? "Rain" : "Dry"))}</div>
            ${weatherBadge}
            ${slotsHtml}
          </div>`;
      })
      .join("");
  }

  async function parseJsonSafe(resp) {
    try {
      return await resp.json();
    } catch (_err) {
      return null;
    }
  }

  async function loadHealth() {
    try {
      const resp = await fetch("/health");
      const data = await parseJsonSafe(resp);
      if (resp.ok && data) {
        updateDemoBadge(data.mode);
        if (data.hourly_rate_pence) {
          setHourlyRatePence(data.hourly_rate_pence);
        }
      }
    } catch (_err) {
      // keep default demo state
    }
  }

  async function loadCalendar() {
    try {
      let resp = await fetch("/api/calendar");
      let data = await parseJsonSafe(resp);
      if (!resp.ok || !data || (!Array.isArray(data.week) && !Array.isArray(data.days))) {
        resp = await fetch("/calendar");
        data = await parseJsonSafe(resp);
      }
      if (!resp.ok || !data) {
        if (bookingMsgEl) {
          bookingMsgEl.classList.add("is-error");
          bookingMsgEl.textContent = "Failed to load calendar.";
        }
        return;
      }
      const normalized = normalizeCalendarPayload(data);
      renderCalendar(normalized);
    } catch (_err) {
      if (bookingMsgEl) {
        bookingMsgEl.classList.add("is-error");
        bookingMsgEl.textContent = "Network error while loading calendar.";
      }
    }
  }

  if (photoInput) {
    photoInput.addEventListener("change", () => {
      setErrorMessage("");
      const file = photoInput.files && photoInput.files[0];
      if (!file) {
        selectedFile = null;
        return;
      }
      useSample = false;
      selectedFile = file;
      if (sampleBtn) {
        sampleBtn.classList.remove("sample-active");
        sampleBtn.setAttribute("aria-pressed", "false");
      }
      if (photoFilenameLabel) {
        photoFilenameLabel.innerHTML = `<code>${escapeHtml(file.name)}</code> · Uploaded Photo`;
      }
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === "string" && uploadedPhotoImg && sampleGardenSvg) {
          uploadedPhotoImg.src = reader.result;
          uploadedPhotoImg.style.display = "block";
          sampleGardenSvg.style.display = "none";
        }
      };
      reader.readAsDataURL(file);
    });
  }

  if (sampleBtn) {
    sampleBtn.addEventListener("click", (event) => {
      event.preventDefault();
      useSample = true;
      selectedFile = null;
      if (photoInput) {
        photoInput.value = "";
      }
      sampleBtn.classList.add("sample-active");
      sampleBtn.setAttribute("aria-pressed", "true");
      setErrorMessage("");
      if (uploadedPhotoImg && sampleGardenSvg) {
        uploadedPhotoImg.style.display = "none";
        sampleGardenSvg.style.display = "block";
      }
      if (photoFilenameLabel) {
        photoFilenameLabel.innerHTML =
          "<code>sample_garden.png</code> (Sample Garden Selected)";
      }
    });
  }

  if (analyseBtn) {
    analyseBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      setErrorMessage("");

      const fileFromInput =
        (photoInput && photoInput.files && photoInput.files[0]) || selectedFile;

      if (!useSample && !fileFromInput) {
        renderTasks([]);
        setErrorMessage(
          "Please select a garden photo or click 'Use sample garden' before analysing."
        );
        return;
      }

      analyseBtn.disabled = true;
      const originalText = analyseBtn.textContent;
      analyseBtn.textContent = "Analysing...";

      try {
        const formData = new FormData();
        if (useSample) {
          try {
            const sampleResp = await fetch("/static/sample_garden.png");
            if (sampleResp.ok) {
              const sampleBlob = await sampleResp.blob();
              formData.append("image", sampleBlob, "sample_garden.png");
            }
          } catch (_fetchErr) {
            // fallback to use_sample form field
          }
          formData.append("use_sample", "true");
        } else if (fileFromInput) {
          formData.append("image", fileFromInput, fileFromInput.name || "upload.png");
        }

        const resp = await fetch("/api/analyse", {
          method: "POST",
          body: formData,
        });
        const data = await parseJsonSafe(resp);

        if (data && data.mode) {
          updateDemoBadge(data.mode);
        }
        if (data && data.hourly_rate_pence) {
          setHourlyRatePence(data.hourly_rate_pence);
        }

        if (!resp.ok || !data) {
          const errMsg =
            (data && data.error && data.error.message) ||
            (data && data.detail) ||
            (data && data.message) ||
            "Failed to analyse garden photo.";
          renderTasks([]);
          setErrorMessage(errMsg);
          return;
        }

        if (data.is_garden === false) {
          renderTasks([]);
          setErrorMessage(
            data.message || "No garden detected in this photo - nothing to quote."
          );
          return;
        }

        setErrorMessage("");
        renderTasks(data.tasks || []);
      } catch (_err) {
        renderTasks([]);
        setErrorMessage("Network error while analysing photo.");
      } finally {
        analyseBtn.disabled = false;
        analyseBtn.textContent = originalText || "Analyse";
      }
    });
  }

  if (tbody) {
    tbody.addEventListener("input", (event) => {
      const target = event.target;
      if (
        target &&
        (target.matches('[data-testid="task-hours"]') ||
          target.matches('[data-testid="task-tick"]'))
      ) {
        recalculateClientTotals();
      }
    });

    tbody.addEventListener("change", (event) => {
      const target = event.target;
      if (
        target &&
        (target.matches('[data-testid="task-hours"]') ||
          target.matches('[data-testid="task-tick"]'))
      ) {
        recalculateClientTotals();
      }
    });
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      recalculateClientTotals();
    });
  }

  if (bookBtn) {
    bookBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      if (isBookingInFlight || isBookedForCurrentQuote || bookBtn.disabled) {
        return;
      }

      const summary = recalculateClientTotals();
      if (summary.hasValidationError || !summary.anyChecked || summary.totalHours <= 0) {
        bookBtn.disabled = true;
        return;
      }

      isBookingInFlight = true;
      bookBtn.disabled = true;
      if (bookingMsgEl) {
        bookingMsgEl.classList.remove("is-error");
        bookingMsgEl.textContent = "Booking...";
      }

      try {
        const resp = await fetch("/api/book", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ hours: summary.totalHours }),
        });
        const data = await parseJsonSafe(resp);

        if (!resp.ok || !data) {
          const errMsg =
            (data && data.error && data.error.message) ||
            (data && data.detail) ||
            (data && data.message) ||
            "Failed to book slot.";
          setErrorMessage(errMsg);
          if (bookingMsgEl) {
            bookingMsgEl.classList.add("is-error");
            bookingMsgEl.textContent = errMsg;
          }
          bookBtn.disabled = false;
          return;
        }

        if (!data.slot) {
          const noSlotMsg =
            data.message || "No weather-safe slot available for this duration.";
          setErrorMessage(noSlotMsg);
          if (bookingMsgEl) {
            bookingMsgEl.classList.add("is-error");
            bookingMsgEl.textContent = noSlotMsg;
          }
          bookBtn.disabled = false;
          return;
        }

        isBookedForCurrentQuote = true;
        const dayLabel = getDayLabelForDate(data.slot.date);
        currentBookedSlot = {
          date: data.slot.date,
          start: data.slot.start,
          end: data.slot.end,
          label: dayLabel,
        };
        bookBtn.textContent = "Booked";
        bookBtn.disabled = true;
        setErrorMessage("");
        if (bookingMsgEl) {
          bookingMsgEl.classList.remove("is-error");
          bookingMsgEl.textContent =
            data.message ||
            `Booked for ${dayLabel}, ${data.slot.start}–${data.slot.end}.`;
        }
        renderCalendar(currentWeek);
        updateQuoteMessage();
      } catch (_err) {
        const netMsg = "Network error while booking slot.";
        setErrorMessage(netMsg);
        if (bookingMsgEl) {
          bookingMsgEl.classList.add("is-error");
          bookingMsgEl.textContent = netMsg;
        }
        bookBtn.disabled = false;
      } finally {
        isBookingInFlight = false;
        if (isBookedForCurrentQuote) {
          bookBtn.disabled = true;
        }
      }
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      const text = (quoteMessageEl && quoteMessageEl.textContent) || "";
      let copied = false;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          copied = true;
        } catch (_err) {
          copied = false;
        }
      }
      if (!copied) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand("copy");
          copied = true;
        } catch (_e) {
          copied = false;
        }
        document.body.removeChild(ta);
      }
      copyBtn.textContent = "Copied!";
      if (copyResetTimer) {
        clearTimeout(copyResetTimer);
      }
      copyResetTimer = setTimeout(() => {
        copyBtn.textContent = "Copy";
      }, 2000);
    });
  }

  setHourlyRatePence(DEFAULT_HOURLY_RATE_PENCE);
  recalculateClientTotals();
  loadHealth();
  loadCalendar();
})();
