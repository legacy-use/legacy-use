// Resolution validation and recommendation utilities

export const RECOMMENDED_RESOLUTION = {
  width: 1024,
  height: 768,
  name: 'XGA (1024x768)',
  description: 'Standard resolution for optimal results'
};

export const COMMON_RESOLUTIONS = {
  XGA: { width: 1024, height: 768, name: 'XGA (1024×768)', description: 'Standard 4:3 - Recommended' },
  WXGA: { width: 1280, height: 800, name: 'WXGA (1280×800)', description: 'Widescreen 16:10' },
  FWXGA: { width: 1366, height: 768, name: 'FWXGA (1366×768)', description: 'Full Wide XGA ~16:9' },
  HD: { width: 1920, height: 1080, name: 'Full HD (1920×1080)', description: 'High Definition 16:9' },
  CUSTOM: { width: 0, height: 0, name: 'Custom', description: 'Custom resolution' }
};

/**
 * Check if the given resolution is optimal (matches recommended resolution)
 * @param {number} width - Width in pixels
 * @param {number} height - Height in pixels
 * @returns {boolean} True if resolution is optimal
 */
export const isOptimalResolution = (width, height) => {
  return width === RECOMMENDED_RESOLUTION.width && height === RECOMMENDED_RESOLUTION.height;
};

/**
 * Get resolution recommendation message
 * @param {number} width - Width in pixels
 * @param {number} height - Height in pixels
 * @returns {object} Object with severity and message
 */
export const getResolutionRecommendation = (width, height) => {
  if (isOptimalResolution(width, height)) {
    return {
      severity: 'success',
      message: `Using recommended resolution: ${RECOMMENDED_RESOLUTION.name} for optimal results.`
    };
  }
  
  // Check if it's a common resolution
  const commonRes = Object.values(COMMON_RESOLUTIONS).find(res => 
    res.width === width && res.height === height
  );
  
  if (commonRes && commonRes.name !== 'Custom') {
    return {
      severity: 'warning',
      message: `Currently using ${commonRes.name}. For optimal results, consider using ${RECOMMENDED_RESOLUTION.name}.`
    };
  }
  
  return {
    severity: 'warning',
    message: `Currently using custom resolution (${width}×${height}). For optimal results, we recommend ${RECOMMENDED_RESOLUTION.name}.`
  };
};

/**
 * Get resolution type/name for display
 * @param {number} width - Width in pixels
 * @param {number} height - Height in pixels
 * @returns {string} Resolution type name
 */
export const getResolutionType = (width, height) => {
  const commonRes = Object.values(COMMON_RESOLUTIONS).find(res => 
    res.width === width && res.height === height
  );
  
  if (commonRes) {
    return commonRes.name;
  }
  
  return `Custom (${width}×${height})`;
};

/**
 * Set resolution to recommended values
 * @returns {object} Object with width and height
 */
export const getRecommendedResolution = () => {
  return {
    width: RECOMMENDED_RESOLUTION.width,
    height: RECOMMENDED_RESOLUTION.height
  };
};