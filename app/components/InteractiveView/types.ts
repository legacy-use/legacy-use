export interface ToolResult {
  output?: string;
  error?: string;
  base64_image?: string;
}

export interface CoordinateInput {
  x: number;
  y: number;
}

export interface KeyboardSequenceStep {
  id: string;
  type: 'text' | 'key';
  content: string;
  delay?: number;
}

export const SPECIAL_KEYS = {
  tab: 'Tab',
  enter: 'Return',
  space: 'space',
  escape: 'Escape',
  backspace: 'BackSpace',
  delete: 'Delete',
  home: 'Home',
  end: 'End',
  pageup: 'Page_Up',
  pagedown: 'Page_Down',
  arrowup: 'Up',
  arrowdown: 'Down',
  arrowleft: 'Left',
  arrowright: 'Right',
  f1: 'F1',
  f2: 'F2',
  f3: 'F3',
  f4: 'F4',
  f5: 'F5',
  f6: 'F6',
  f7: 'F7',
  f8: 'F8',
  f9: 'F9',
  f10: 'F10',
  f11: 'F11',
  f12: 'F12',
  'ctrl+c': 'ctrl+c',
  'ctrl+v': 'ctrl+v',
  'ctrl+x': 'ctrl+x',
  'ctrl+z': 'ctrl+z',
  'ctrl+y': 'ctrl+y',
  'ctrl+a': 'ctrl+a',
  'ctrl+s': 'ctrl+s',
  'alt+tab': 'alt+Tab',
  'shift+tab': 'shift+Tab',
} as const;
