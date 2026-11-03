import { accentPresets } from "./accent-palette";

export const themeInitializationScript = `(function(){var root=document.documentElement;root.dataset.theme="light";root.dataset.accent="purple";try{var saved=localStorage.getItem("ielts-theme");root.dataset.theme=saved==="dark"?"dark":"light";var accent=localStorage.getItem("ielts-accent");root.dataset.accent=${JSON.stringify(accentPresets)}.indexOf(accent)!==-1?accent.toLowerCase():"purple"}catch(e){}})();`;
