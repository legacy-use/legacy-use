import ArrowBackIosNewIcon from '@mui/icons-material/ArrowBackIosNew';
import ArrowForwardIosIcon from '@mui/icons-material/ArrowForwardIos';
import BuildIcon from '@mui/icons-material/Build';
import ChatIcon from '@mui/icons-material/Chat';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CloseIcon from '@mui/icons-material/Close';
import ErrorIcon from '@mui/icons-material/Error';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import HttpIcon from '@mui/icons-material/Http';
import InfoIcon from '@mui/icons-material/Info';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import MouseIcon from '@mui/icons-material/Mouse';
import PauseCircleIcon from '@mui/icons-material/PauseCircle';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import SettingsIcon from '@mui/icons-material/Settings';
import TextSnippetIcon from '@mui/icons-material/TextSnippet';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Modal from '@mui/material/Modal';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// Custom component for displaying logs with syntax highlighting
const LogViewer = ({ logs }) => {
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  type Screenshot = { logIndex: number; data: any; format: string };
  const [expandedImage, setExpandedImage] = useState<Screenshot | null>(null);
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [userHasScrolled, setUserHasScrolled] = useState<boolean>(false);

  // Group related logs together (can be defined outside or memoized if needed)
  const groupRelatedLogs = useCallback((logsToGroup: any[]) => {
    const groupedLogs: any[] = [];
    let i = 0;

    while (i < logsToGroup.length) {
      const currentLog = logsToGroup[i];

      // For ui_not_as_expected, we want to keep both messages separate
      if (
        currentLog?.type === 'message' &&
        currentLog?.content?.type === 'tool_use' &&
        currentLog?.content?.name === 'ui_not_as_expected'
      ) {
        groupedLogs.push(currentLog);
        i++;
        continue;
      }

      if (
        typeof currentLog === 'object' &&
        currentLog.type === 'message' &&
        currentLog.content &&
        currentLog.content.type === 'tool_use'
      ) {
        if (i + 1 < logsToGroup.length) {
          const nextLog = logsToGroup[i + 1];

          // Check if this is a tool_use followed by a tool result
          if (
            typeof nextLog === 'object' &&
            nextLog.type === 'tool_use' &&
            nextLog.content &&
            currentLog.content.id &&
            nextLog.content.tool_id === currentLog.content.id
          ) {
            const enhancedLog = {
              ...currentLog,
              tool_result: nextLog,
              // Create a combined ID to ensure stability when both logs are merged
              id: `${currentLog.id || ''}-${nextLog.id || ''}`,
            };

            groupedLogs.push(enhancedLog);
            i += 2;
            continue;
          }

          // Special handling for extraction tool
          if (
            currentLog.content.name === 'extraction' &&
            typeof nextLog === 'object' &&
            nextLog.type === 'tool_use' &&
            nextLog.content
          ) {
            // Check for matching ID with extraction tool
            const currentId = currentLog.content.id;
            const isMatchingResult = nextLog.content.tool_id === currentId;

            if (isMatchingResult) {
              const enhancedLog = {
                ...currentLog,
                tool_result: nextLog,
                // Create a combined ID to ensure stability when both logs are merged
                id: `${currentLog.id || ''}-${nextLog.id || ''}`,
              };

              groupedLogs.push(enhancedLog);
              i += 2;
              continue;
            }
          }
        }
      }

      groupedLogs.push(currentLog);
      i++;
    }

    return groupedLogs;
  }, []);

  // Memoize processed logs to avoid recalculation and ensure stable dependency for effects
  const processedLogs = useMemo(() => {
    return groupRelatedLogs(logs || []);
  }, [logs, groupRelatedLogs]);

  // Extract screenshots from processed logs
  useEffect(() => {
    const extractedScreenshots: Screenshot[] = [];
    processedLogs.forEach((log, index) => {
      if (hasImage(log)) {
        const data = getImageData(log);
        if (data) {
          // Ensure data is not null before proceeding
          const format = getImageFormat(data);
          extractedScreenshots.push({ logIndex: index, data, format });
        }
      }
    });
    setScreenshots(extractedScreenshots);
    // Reset expanded image if the logs change and the current expanded image is no longer valid
    if (expandedImage && !extractedScreenshots.some(s => s.logIndex === expandedImage.logIndex)) {
      setExpandedImage(null);
    }
  }, [processedLogs, expandedImage]); // Add expandedImage dependency for reset logic

  // --- Navigation Logic ---
  const navigateToScreenshot = useCallback(
    (direction: 'prev' | 'next') => {
      if (!expandedImage || screenshots.length <= 1) return; // No navigation if 0 or 1 screenshot

      const currentScreenshotArrayIndex = screenshots.findIndex(
        s => s.logIndex === expandedImage.logIndex,
      );
      if (currentScreenshotArrayIndex === -1) return; // Safety check

      let nextScreenshotArrayIndex: number;
      if (direction === 'prev') {
        nextScreenshotArrayIndex =
          (currentScreenshotArrayIndex - 1 + screenshots.length) % screenshots.length;
      } else {
        // direction === 'next'
        nextScreenshotArrayIndex = (currentScreenshotArrayIndex + 1) % screenshots.length;
      }

      const nextScreenshot = screenshots[nextScreenshotArrayIndex];
      setExpandedImage({
        logIndex: nextScreenshot.logIndex,
        data: nextScreenshot.data,
        format: nextScreenshot.format,
      });
    },
    [expandedImage, screenshots],
  );

  // Handle keyboard navigation for the modal
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') {
        navigateToScreenshot('prev');
      } else if (event.key === 'ArrowRight') {
        navigateToScreenshot('next');
      }
    },
    [navigateToScreenshot],
  ); // Depend on the stable navigateToScreenshot function

  // Add and remove keyboard listener when modal opens/closes
  useEffect(() => {
    if (expandedImage) {
      window.addEventListener('keydown', handleKeyDown);
    } else {
      window.removeEventListener('keydown', handleKeyDown);
    }

    // Cleanup listener on component unmount or when dependencies change
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [expandedImage, handleKeyDown]);

  // Detect when user manually scrolls
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current;
    if (!scrollContainer) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
      // Check if user has scrolled up (not at the bottom)
      // Use a slightly larger threshold to better detect "close to bottom"
      const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 20;

      setUserHasScrolled(!isAtBottom);
    };

    scrollContainer.addEventListener('scroll', handleScroll);

    // Initial check
    handleScroll();

    return () => {
      scrollContainer.removeEventListener('scroll', handleScroll);
    };
  }, []);

  // Create a memoized value to track when logs actually change length
  const logsLength = useMemo(() => logs?.length || 0, [logs]);

  // Auto-scroll to bottom when logs change (if user hasn't scrolled up)
  useEffect(() => {
    // Only auto-scroll if user is already at the bottom or hasn't scrolled manually
    if (!userHasScrolled && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logsLength, userHasScrolled]);

  // Function to manually scroll to bottom
  const scrollToBottom = () => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
      setUserHasScrolled(false);
    }
  };

  // Early return must be AFTER hooks
  if (!logs || logs.length === 0) {
    return <Typography variant="body2">No logs available</Typography>;
  }

  // Helper function to recursively replace base64 image data with a placeholder
  const hideBase64Images = (obj: any) => {
    if (!obj || typeof obj !== 'object') return obj;

    const result: any = Array.isArray(obj) ? [...obj] : { ...obj };

    for (const key in result) {
      if (
        (key === 'base64_image' || key.endsWith('_image')) &&
        typeof result[key] === 'string' &&
        result[key].length > 100
      ) {
        result[key] = '... [base64 image data hidden] ...';
      } else if (typeof result[key] === 'object' && result[key] !== null) {
        result[key] = hideBase64Images(result[key]);
      }
    }

    return result;
  };

  // Function to properly format log entries
  const formatLog = (log: any) => {
    if (typeof log === 'string') {
      return log;
    } else if (typeof log === 'object' && log !== null) {
      // Handle API execution logs
      if (log.type === 'system') {
        if (log.content?.message_type === 'initial_prompt') {
          return `Initial Prompt:\n${log.content.prompt}`;
        }
        if (typeof log.content === 'string' && log.content.includes('Starting execution of API:')) {
          const apiName = log.content.split('API:')[1]?.trim() || '';
          return `Starting API: ${apiName}`;
        }
        if (
          typeof log.content === 'string' &&
          log.content.includes('Executing API with parameters:')
        ) {
          try {
            // Extract parameters from the log content string
            const paramsText =
              log.content.split('Executing API with parameters:')[1]?.trim() || '{}';
            const params = paramsText !== '{}' ? JSON.parse(paramsText) : {};
            return Object.keys(params).length > 0
              ? `API parameters: ${JSON.stringify(params)}`
              : 'API parameters: {}';
          } catch {
            // Fallback to displaying raw content if parsing fails
            return log.content;
          }
        }
        if (log.content?.includes('API Credits Exceeded')) {
          return "You've run out of credits...\nBook a demo with us -> https://legacy-use.com/";
        }
        if (typeof log.content === 'string') {
          return log.content;
        }
      }

      // Handle text messages
      if (log.type === 'message' && log.content && log.content.type === 'text') {
        return log.content.text;
      }

      // Handle tool uses
      if (log.type === 'message' && log.content && log.content.type === 'tool_use') {
        const action = log.content.input?.action;

        // Handle extraction tool specifically
        if (log.content.name === 'extraction') {
          try {
            const extractionData = log.content.input?.data;
            return `Extraction tool called with data: ${JSON.stringify(extractionData, null, 2)}`;
          } catch {
            return 'Extraction tool called';
          }
        }

        // Handle ui_not_as_expected tool
        if (log.content.name === 'ui_not_as_expected') {
          return `UI Discrepancy: ${log.content.input?.reasoning || 'No reason provided'}`;
        }

        // Handle custom action tool
        if (log.content.name === 'custom_action') {
          return `Custom action: "${log.content.input?.action_name}"`;
        }

        // Check for extraction tool result in combined log entry
        if (log.tool_result?.content && log.content.name === 'extraction') {
          try {
            // Try to extract and format the extraction result
            const resultContent = log.tool_result.content;
            if (Array.isArray(resultContent)) {
              const textBlock = resultContent.find((item: any) => item.type === 'text');
              if (textBlock?.text) {
                try {
                  const jsonData = JSON.parse(textBlock.text);
                  return `Extraction data: ${JSON.stringify(jsonData, null, 2)}`;
                } catch {
                  return `Extraction data: ${textBlock.text}`;
                }
              }
            }
          } catch {
            // Fallback
            return `Extraction tool with result (parsing failed)`;
          }
        }

        switch (action) {
          case 'screenshot':
            return 'Taking screenshot...';
          case 'mouse_move': {
            const coordinate = log.content.input?.coordinate;
            if (coordinate && coordinate.length === 2) {
              const [x, y] = coordinate;
              return `Moving to ${x}:${y}`;
            }
            return 'Moving mouse';
          }
          case 'left_click':
            return 'Left clicking';
          case 'left_click_drag':
            return 'Dragging with left button';
          case 'right_click':
            return 'Right clicking';
          case 'middle_click':
            return 'Middle clicking';
          case 'double_click':
            return 'Double clicking';
          case 'type':
            return `Typing: "${log.content.input?.text || ''}"`;
          case 'key':
            return `Pressing key: ${log.content.input?.text || 'unknown'}`;
          case 'cursor_position':
            return 'Getting cursor position';
          case 'wait':
            return `Waiting ${log.content.input?.duration}s`;
          case 'open':
            return `Opening: "${log.content.input?.path}"`;
          case 'close':
            return `Closing: "${log.content.input?.path}"`;
          default:
            return `${action || 'Unknown action'}`;
        }
      }

      // Handle tool_use results
      if (log.type === 'tool_use') {
        // Check for ui_not_as_expected tool results
        if (log.content?.output) {
          return log.content.output;
        }

        // Check for extraction tool results specifically
        if (
          log.content?.tool_id &&
          typeof log.content.tool_id === 'string' &&
          log.content.tool_id.includes('extraction')
        ) {
          try {
            // Try to extract and format the JSON data from the result
            if (Array.isArray(log.content.content) && log.content.content.length > 0) {
              const textContent = log.content.content.find((item: any) => item.type === 'text');
              if (textContent?.text) {
                try {
                  const jsonData = JSON.parse(textContent.text);
                  return `Extraction result: ${JSON.stringify(jsonData, null, 2)}`;
                } catch {
                  return `Extraction result: ${textContent.text}`;
                }
              }
            }
          } catch {
            return 'Extraction tool result (parsing error)';
          }
        }

        return 'Tool result';
      }

      // Handle result logs
      if (log.type === 'result') {
        return `Result: ${JSON.stringify(log.content)}`;
      }

      // If it's a structured log with content
      if (log.content !== undefined) {
        const content = log.content;
        if (typeof content === 'string') {
          return content;
        } else {
          try {
            const processedContent = hideBase64Images(content);
            return JSON.stringify(processedContent);
          } catch {
            return String(content);
          }
        }
      } else {
        try {
          const processedLog = hideBase64Images(log);
          return JSON.stringify(processedLog);
        } catch {
          return String(log);
        }
      }
    } else {
      return String(log);
    }
  };

  // Function to determine log icon based on type
  const getLogIcon = (log: any) => {
    if (typeof log === 'object' && log !== null) {
      const type = log.type;
      const content = formatLog(log);

      // Handle extraction tool specifically
      if (
        log.type === 'message' &&
        log.content &&
        log.content.type === 'tool_use' &&
        log.content.name === 'extraction'
      ) {
        return <InfoIcon fontSize="small" sx={{ color: '#12b886', mr: 1 }} />;
      }

      // For logs with tool_result, use more specific icons based on the action
      if (log.tool_result && log.content && log.content.type === 'tool_use' && log.content.input) {
        // If it's an extraction tool result
        if (log.content.name === 'extraction') {
          return <InfoIcon fontSize="small" sx={{ color: '#12b886', mr: 1 }} />;
        }

        const action = log.content.input.action;
        switch (action) {
          case 'screenshot':
            return <PhotoCameraIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          case 'mouse_move':
          case 'left_click':
          case 'left_click_drag':
          case 'right_click':
          case 'middle_click':
          case 'double_click':
          case 'cursor_position':
            return <MouseIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          case 'type':
          case 'key':
            return <KeyboardIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          case 'wait':
            return <HourglassEmptyIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          case 'open':
            return <FolderOpenIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          case 'close':
            return <CloseIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          default:
            return <BuildIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
        }
      }

      if (type === 'error') return <ErrorIcon fontSize="small" sx={{ color: '#ff6b6b', mr: 1 }} />;
      if (type === 'system') {
        // Special handling for initial prompt logs
        if (log.content?.message_type === 'initial_prompt') {
          return <TextSnippetIcon fontSize="small" sx={{ color: '#4dabf5', mr: 1 }} />;
        }
        return <SettingsIcon fontSize="small" sx={{ color: '#ffa94d', mr: 1 }} />;
      }
      if (type === 'message') {
        if (log.content && log.content.type === 'text') {
          return <ChatIcon fontSize="small" sx={{ color: '#4dabf5', mr: 1 }} />;
        }
        if (log.content && log.content.type === 'tool_use') {
          // Handle ui_not_as_expected tool
          if (log.content.name === 'ui_not_as_expected') {
            return <PauseCircleIcon fontSize="small" sx={{ color: '#ffa94d', mr: 1 }} />;
          }

          const action = log.content.input?.action;
          switch (action) {
            case 'screenshot':
              return <PhotoCameraIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
            case 'mouse_move':
            case 'left_click':
            case 'left_click_drag':
            case 'right_click':
            case 'middle_click':
            case 'double_click':
            case 'cursor_position':
              return <MouseIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
            case 'type':
            case 'key':
              return <KeyboardIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
            case 'wait':
              return <HourglassEmptyIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
            case 'open':
              return <FolderOpenIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
            case 'close':
              return <CloseIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
            default:
              return <BuildIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
          }
        }
        return <ChatIcon fontSize="small" sx={{ color: '#4dabf5', mr: 1 }} />;
      }
      if (type === 'result')
        return <CheckCircleIcon fontSize="small" sx={{ color: '#69db7c', mr: 1 }} />;
      if (type === 'tool_use')
        return <BuildIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
      if (type === 'http_exchange')
        return <HttpIcon fontSize="small" sx={{ color: '#69db7c', mr: 1 }} />;

      // Fallback based on string content (less reliable)
      const logString = typeof content === 'string' ? content : JSON.stringify(log);
      if (logString.includes('[ERROR]'))
        return <ErrorIcon fontSize="small" sx={{ color: '#ff6b6b', mr: 1 }} />;
      if (logString.includes('[INFO]'))
        return <InfoIcon fontSize="small" sx={{ color: '#4dabf5', mr: 1 }} />;
      if (logString.includes('[SYSTEM]'))
        return <SettingsIcon fontSize="small" sx={{ color: '#ffa94d', mr: 1 }} />;
      if (logString.includes('[HTTP]'))
        return <HttpIcon fontSize="small" sx={{ color: '#69db7c', mr: 1 }} />;
      if (logString.includes('[TOOL]'))
        return <BuildIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
    } else if (typeof log === 'string') {
      if (log.includes('[ERROR]'))
        return <ErrorIcon fontSize="small" sx={{ color: '#ff6b6b', mr: 1 }} />;
      if (log.includes('[INFO]'))
        return <InfoIcon fontSize="small" sx={{ color: '#4dabf5', mr: 1 }} />;
      if (log.includes('[SYSTEM]'))
        return <SettingsIcon fontSize="small" sx={{ color: '#ffa94d', mr: 1 }} />;
      if (log.includes('[HTTP]'))
        return <HttpIcon fontSize="small" sx={{ color: '#69db7c', mr: 1 }} />;
      if (log.includes('[TOOL]'))
        return <BuildIcon fontSize="small" sx={{ color: '#da77f2', mr: 1 }} />;
    }

    return <TextSnippetIcon fontSize="small" sx={{ color: '#e0e0e0', mr: 1 }} />; // Default icon
  };

  // Function to get the base64 image from a log entry
  const getImageData = (log: any) => {
    // Prioritize tool_result if available
    if (log?.tool_result?.content?.base64_image) {
      return log.tool_result.content.base64_image;
    }

    if (typeof log === 'object' && log !== null && log.content) {
      if (typeof log.content === 'object' && log.content !== null) {
        // Direct properties
        if (log.content.base64_image) return log.content.base64_image;
        if (log.content.image) return log.content.image;
        if (log.content.screenshot) return log.content.screenshot;

        // Nested properties (output, result, tool_result)
        if (log.content.output?.base64_image) return log.content.output.base64_image;
        if (log.content.result?.base64_image) return log.content.result.base64_image;
        if (log.content.tool_result?.base64_image) return log.content.tool_result.base64_image;

        // Check keys ending with _image
        for (const key in log.content) {
          if (key.endsWith('_image') && typeof (log.content as any)[key] === 'string') {
            return (log.content as any)[key];
          }
        }
        if (log.content.output) {
          for (const key in log.content.output) {
            if (key.endsWith('_image') && typeof (log.content.output as any)[key] === 'string') {
              return (log.content.output as any)[key];
            }
          }
        }
      }
    }

    return null;
  };

  // Function to check if a log entry has an image (more robust check)
  const hasImage = (log: any) => {
    if (!log || typeof log !== 'object') return false;

    // Check explicit flags first
    if (log.tool_result?.content?.has_image === true) return true;
    if (log.content?.has_image === true) return true;
    if (log.type === 'tool_use' && log.content?.has_image === true) return true;
    if (
      log.type === 'message' &&
      log.content?.type === 'tool_use' &&
      log.content?.has_image === true
    )
      return true;

    // If no explicit flag, try finding image data
    return !!getImageData(log);
  };

  // Function to determine the image format
  const getImageFormat = (base64String: string) => {
    if (!base64String || typeof base64String !== 'string') return 'image/png'; // Default or handle error

    if (base64String.startsWith('/9j/')) {
      return 'image/jpeg';
    } else if (base64String.startsWith('iVBORw0KGgo')) {
      return 'image/png';
    } else if (base64String.startsWith('R0lGODlh')) {
      return 'image/gif';
    } else if (base64String.startsWith('UklGRg')) {
      return 'image/webp';
    } else if (base64String.startsWith('PHN2Zz')) {
      return 'image/svg+xml';
    }
    return 'image/png'; // Default
  };

  // Update handleImageClick to store the logIndex of the clicked image
  const handleImageClick = (logIndex: number) => {
    const screenshot = screenshots.find(s => s.logIndex === logIndex);
    if (screenshot) {
      setExpandedImage({
        logIndex: screenshot.logIndex,
        data: screenshot.data,
        format: screenshot.format,
      });
    }
  };

  // Function to format timestamp for display
  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  return (
    <Box
      ref={scrollContainerRef}
      sx={{
        backgroundColor: '#1a1a1a',
        color: '#f5f5f5',
        padding: 2,
        maxHeight: '800px',
        overflowY: 'auto',
        fontFamily: 'monospace',
        fontSize: '13px',
        position: 'relative',
      }}
    >
      {/* Scroll to bottom button */}
      <IconButton
        onClick={scrollToBottom}
        sx={{
          position: 'sticky',
          bottom: 16,
          left: '50%',
          transform: 'translateX(-50%)',
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          color: 'white',
          '&:hover': {
            backgroundColor: 'rgba(0, 0, 0, 0.9)',
          },
          zIndex: 2,
        }}
      >
        <KeyboardArrowDownIcon />
      </IconButton>

      {/* Render the grouped logs */}
      {processedLogs.map((log, index) => {
        // Format the log content and get appropriate icon
        const logContent = formatLog(log);
        const icon = getLogIcon(log);
        const currentHasImage = hasImage(log); // Check once per log entry

        // Check if this is an extraction tool
        const isExtractionTool =
          log.type === 'message' &&
          log.content?.type === 'tool_use' &&
          log.content?.name === 'extraction';

        // Check if this is an extraction tool result
        const isExtractionResult =
          log.type === 'tool_use' && log.content?.tool_id?.includes('extraction');

        // Check if this is an initial prompt log
        const isInitialPrompt =
          log.type === 'system' && log.content?.message_type === 'initial_prompt';

        // Generate a unique key for each log entry
        const logKey = log.id || log.timestamp || `log-${index}`;

        return (
          <Box
            key={logKey}
            sx={{
              py: 0.5,
              borderBottom: '1px solid #333',
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: isInitialPrompt
                ? 'rgba(73, 171, 245, 0.1)'
                : isExtractionTool || isExtractionResult
                  ? 'rgba(18, 184, 134, 0.1)'
                  : 'inherit',
            }}
          >
            {/* Log entry header with timestamp and icon */}
            <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 0.5 }}>
              <Tooltip title={formatTimestamp(log.timestamp)} arrow placement="top">
                <Box sx={{ display: 'inline-flex' }}>{icon}</Box>
              </Tooltip>

              <Typography
                component="pre"
                sx={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontFamily: 'monospace',
                  fontSize: 'inherit',
                  flexGrow: 1,
                }}
              >
                {logContent}
              </Typography>

              {/* Show zoom button for logs with images */}
              {currentHasImage && (
                <IconButton
                  size="small"
                  onClick={() => handleImageClick(index)}
                  sx={{ ml: 1 }}
                  aria-label="Zoom in on image"
                >
                  <ZoomInIcon fontSize="small" />
                </IconButton>
              )}
            </Box>

            {/* Render images if present */}
            {currentHasImage && (
              <Box
                component="img"
                src={`data:${getImageFormat(getImageData(log))};base64,${getImageData(log)}`}
                alt={`Screenshot in log entry ${index + 1}`}
                sx={{
                  maxWidth: '100%',
                  mt: 1,
                  cursor: 'pointer',
                  border: '1px solid #555',
                }}
                onClick={() => handleImageClick(index)}
                loading="lazy"
              />
            )}
          </Box>
        );
      })}

      {/* REF for auto-scrolling */}
      <div ref={logEndRef} />

      {/* Modal for expanded images */}
      <Modal
        open={expandedImage !== null}
        onClose={() => setExpandedImage(null)}
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Box sx={{ outline: 'none', maxWidth: '95vw', maxHeight: '95vh' }}>
          {expandedImage && (
            <Box sx={{ position: 'relative' }}>
              <Box
                component="img"
                src={`data:${expandedImage.format};base64,${expandedImage.data}`}
                alt={`Expanded Screenshot ${screenshots.findIndex(s => s.logIndex === expandedImage.logIndex) + 1} of ${screenshots.length}`}
                sx={{
                  display: 'block',
                  maxWidth: '100%',
                  maxHeight: '95vh',
                  objectFit: 'contain',
                }}
              />

              {screenshots.length > 1 && (
                <>
                  <IconButton
                    onClick={() => navigateToScreenshot('prev')}
                    sx={{
                      position: 'absolute',
                      top: '50%',
                      left: 16,
                      transform: 'translateY(-50%)',
                      backgroundColor: 'rgba(0, 0, 0, 0.5)',
                      color: 'white',
                      '&:hover': {
                        backgroundColor: 'rgba(0, 0, 0, 0.7)',
                      },
                    }}
                    aria-label="Previous screenshot"
                  >
                    <ArrowBackIosNewIcon />
                  </IconButton>

                  <IconButton
                    onClick={() => navigateToScreenshot('next')}
                    sx={{
                      position: 'absolute',
                      top: '50%',
                      right: 16,
                      transform: 'translateY(-50%)',
                      backgroundColor: 'rgba(0, 0, 0, 0.5)',
                      color: 'white',
                      '&:hover': {
                        backgroundColor: 'rgba(0, 0, 0, 0.7)',
                      },
                    }}
                    aria-label="Next screenshot"
                  >
                    <ArrowForwardIosIcon />
                  </IconButton>
                </>
              )}

              {screenshots.length > 1 && expandedImage && (
                <Typography
                  variant="caption"
                  sx={{
                    color: 'rgba(255, 255, 255, 0.7)',
                    mt: 1,
                    textAlign: 'center',
                    display: 'block',
                  }}
                >
                  Use ← → arrow keys to navigate
                </Typography>
              )}
            </Box>
          )}
        </Box>
      </Modal>
    </Box>
  );
};

export default LogViewer;
