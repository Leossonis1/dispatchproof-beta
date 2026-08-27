(function () {
  function pluralize(count, singular, plural) {
    return count === 1 ? singular : plural;
  }

  function enhancePhotoCapture(root) {
    const submitInput = root.querySelector('.photo-submit-input');
    const cameraInput = root.querySelector('.photo-camera-input');
    const galleryInput = root.querySelector('.photo-gallery-input');
    const preview = root.querySelector('.field-photo-preview');
    const counter = root.querySelector('.field-photo-counter');

    let minimum = Number(root.dataset.min || 0);
    let files = [];
    let objectUrls = [];

    const supportsTransfer = typeof DataTransfer !== 'undefined';

    function revokeObjectUrls() {
      objectUrls.forEach(url => URL.revokeObjectURL(url));
      objectUrls = [];
    }

    function syncSubmitInput() {
      if (!supportsTransfer) return;
      const transfer = new DataTransfer();
      files.forEach(file => transfer.items.add(file));
      submitInput.files = transfer.files;
    }

    function counterText() {
      const count = files.length;
      if (minimum > 0) {
        if (count >= minimum) {
          return `${count} ${pluralize(count, 'photo', 'photos')} added · requirement met`;
        }
        return `${count} of ${minimum} required photos added`;
      }
      return count === 0
        ? 'No photos added yet'
        : `${count} ${pluralize(count, 'photo', 'photos')} added`;
    }

    function render() {
      revokeObjectUrls();
      preview.innerHTML = '';

      files.forEach((file, index) => {
        if (!file.type.startsWith('image/')) return;

        const card = document.createElement('div');
        card.className = 'field-photo-card';

        const img = document.createElement('img');
        img.alt = `Selected photo ${index + 1}`;
        const url = URL.createObjectURL(file);
        objectUrls.push(url);
        img.src = url;

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'field-photo-remove';
        remove.textContent = 'Remove';
        remove.setAttribute('aria-label', `Remove selected photo ${index + 1}`);
        remove.addEventListener('click', () => {
          files.splice(index, 1);
          syncSubmitInput();
          render();
        });

        card.appendChild(img);
        card.appendChild(remove);
        preview.appendChild(card);
      });

      counter.textContent = counterText();
      root.classList.toggle('photo-requirement-met', minimum > 0 && files.length >= minimum);
      root.classList.toggle('has-field-photos', files.length > 0);
    }

    function addFiles(fileList) {
      Array.from(fileList || []).forEach(file => {
        if (file.type && file.type.startsWith('image/')) {
          files.push(file);
        }
      });

      if (supportsTransfer) {
        syncSubmitInput();
      } else {
        // Modern supported browsers use DataTransfer. This branch keeps the
        // visible source controls usable rather than failing silently.
        root.classList.add('photo-capture-fallback');
      }

      render();
    }

    cameraInput.addEventListener('change', () => {
      addFiles(cameraInput.files);
      if (supportsTransfer) cameraInput.value = '';
    });

    galleryInput.addEventListener('change', () => {
      addFiles(galleryInput.files);
      if (supportsTransfer) galleryInput.value = '';
    });

    root.photoCapture = {
      count: () => supportsTransfer ? files.length : (
        (cameraInput.files ? cameraInput.files.length : 0) +
        (galleryInput.files ? galleryInput.files.length : 0)
      ),
      setMinimum: (value) => {
        minimum = Number(value || 0);
        render();
      }
    };

    render();
  }

  document.querySelectorAll('[data-photo-capture]').forEach(enhancePhotoCapture);
})();
