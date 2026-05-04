// Light switcher
const lightSwitches = document.querySelectorAll('.light-switch');
if (lightSwitches.length > 0) {
  lightSwitches.forEach((lightSwitch, i) => {
    if (localStorage.getItem('dark-mode') === 'true') {
      lightSwitch.checked = true;
    }
    lightSwitch.addEventListener('change', () => {
      const { checked } = lightSwitch;
      lightSwitches.forEach((el, n) => {
        if (n !== i) {
          el.checked = checked;
        }
      });
      if (lightSwitch.checked) {
        document.documentElement.dataset.theme = 'dark';
        localStorage.setItem('dark-mode', true);
        document.dispatchEvent(new CustomEvent('darkMode', { detail: { mode: 'on' } }));
      } else {
        document.documentElement.dataset.theme = 'light';
        localStorage.setItem('dark-mode', false);
        document.dispatchEvent(new CustomEvent('darkMode', { detail: { mode: 'off' } }));
      }
    });
  });
}
