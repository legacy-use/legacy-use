# How to Prompt

### Writing Instructions: Prompt Structure

- **Begin with a one-line summary of the process.**
- For **each step**:
    - **UI to expect**:
        - Describe what the model should see *before* continuing.
        - If views tend to be similar and easy to confuse, include instructions on how to **notice if the wrong view is visible**.
    - **Action**:
        - Describe one single action using one tool.
        - Never combine different tool types in the same step.
            - ✅ *Press the key “BACKSPACE” five times*
            - ✅ *Click the “OK” button*
            - ❌ *Press “BACKSPACE” and then type “Hello”*

---

### Available Tools

These are the predefined tools the model can use to interact with the interface:

- **Type**
    
    Enters plain text input into a field.
    
    Example: *Type the text: “Example text”*
    
- **Press key**
    
    Simulates pressing a key or shortcut on the keyboard.
    
    Example: *Press the key: “RETURN”*
    
    This tool also supports commands like: *Press the key “BACKSPACE” **five times***
    
- **Click**
    
    Clicks on an element with the cursor.
    
    Example: *Click on the “Open” button in the top left toolbar*
    
    Also available:
    
    - *Double click*
    - *Right click*

- **Drag and drop**
    
    Moves an element by dragging it with the cursor.
    > **Before use**: Ensure the element is selected and the cursor is positioned over it (typically done with the left-click tool first).

    Example: *Click on the file "sample-1.pdf" and drag it into the "work" folder.*
    
- **Scroll up / Scroll down**
    
    Scrolls the screen in the corresponding direction.
    
    Example: *Scroll down on the shopping list on the left*
    
- **ui_not_as_expected**
    
    Use this tool **if the UI does not match the expected description**—for example, if the wrong tab is visible, elements are missing, or unexpected popups appear. This prevents the model from performing incorrect or unsafe actions.
    
    **Example:** *If you notice a popup containing a warning message, use the `ui_not_as_expected` tool.*
    
- **extract_tool**
    
    Use this tool at the **end of a process** to return the final result once the expected outcome is confirmed. The model will try to match the format defined in the **response example** section of the API specification.
    
    **Example:** *Now that the data sheet is visible, return the required price information using the `extract_tool`.*
    

> 💡 Tip: Whenever possible, prefer using keyboard shortcuts (press key) over mouse interactions (click).  It is more reliable and less dependent on precise layout positioning.
> 

---

### Using Braces (`{{...}}`)

You can insert dynamic values into the prompt by using double braces:

- `{{documentation_type}}`, `{{date}}`, etc.

These are **placeholders** that will be filled with arguments provided by the **parameter** of the API call during execution.

---

## Prompt Example

### Process: Create a New Entry in a Patient’s Record

> Important: If the UI at any point does not match the expected description, stop and use the ui_not_as_expected tool.
> 

---

### Step 1: Start Patient Selection

**Expected UI:**

Main interface with patient management options.

There should be **no** popups, dialogs, or patient details visible.

**Action:**

Click the **“Patientenauswahl”** button in the top right corner.

---

### Step 2: Search for Patient

**Expected UI:**

A patient search screen with fields for personal info and address. A patient list is visible on the left.

**Action:**

In the search bar below the toolbar (containing “Einstellungen”, “Info”, “Hilfe”, “Fenster”, etc.), type: `{{patient_number}}`

(Do not click—just begin typing immediately.)

---

### Step 3: Open Patient Info

**Expected UI:**

The interface now shows detailed info for the selected patient.

**Action:**

Click the **“Info”** tab (between “Einstellungen” and “Hilfe”).

---

### Step 4: Prepare Form

**Expected UI:**

You're now on the **“Info”** tab. You should see:

- A calendar
- A list of documentation entries
- An insertion field that is already selected and ready for typing

**Make sure** you're *not* on the **“Hilfe”** tab:

- “Hilfe” has a “Kundensupport” button at the bottom.
- “Info” does **not** have a “Kundensupport” button.

**Action:**

Type: `{{date}}{{documentation_type}}`

*(Do not use the mouse. No clicking needed here.)*

---

### Step 5: Confirm Entry

**Expected UI:**

The same “Info” tab as before, but now the new information has been added to the text field.

**Action:**

Press: `RETURN` **two times**, to confirm the entry.

---

### Step 6: Verify Entry Creation

**Expected UI:**

The same “Info” tab, but now the new information has been added to the documentation entries.

**Action:**

Return `ok` using the `extract_tool`.