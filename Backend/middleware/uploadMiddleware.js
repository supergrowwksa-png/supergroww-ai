const multer = require("multer");
const path = require("path");
const fs = require("fs");

// Ensure upload directories exist
const profileDir = "uploads/profile";
const resumeDir = "uploads/resume";

if (!fs.existsSync(profileDir)) fs.mkdirSync(profileDir, { recursive: true });
if (!fs.existsSync(resumeDir)) fs.mkdirSync(resumeDir, { recursive: true });

// ================= STORAGE CONFIG =================
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    if (file.fieldname === "profilePhoto") {
      cb(null, profileDir);
    } else if (file.fieldname === "resume") {
      cb(null, resumeDir);
    } else {
      cb(new Error("Invalid file field"), false);
    }
  },

  filename: (req, file, cb) => {
    const uniqueName =
      Date.now() + "-" + Math.round(Math.random() * 1e9);
    cb(null, uniqueName + path.extname(file.originalname));
  },
});

// ================= FILE FILTER =================
const fileFilter = (req, file, cb) => {
  if (file.fieldname === "profilePhoto") {
    if (!file.mimetype.startsWith("image/")) {
      return cb(new Error("Profile photo must be an image"), false);
    }
  }

  if (file.fieldname === "resume") {
    const allowed = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ];

    if (!allowed.includes(file.mimetype)) {
      return cb(new Error("Resume must be PDF or DOC/DOCX"), false);
    }
  }

  cb(null, true);
};

// ================= MULTER INSTANCE =================
const upload = multer({
  storage,
  fileFilter,
  limits: {
    fileSize: 2 * 1024 * 1024, // 2MB
  },
});

// ================= SAFE FILE DELETE HELPER =================
// (Used when replacing profile photo / resume)
const deleteFileIfExists = (filePath) => {
  if (!filePath) return;

  const fullPath = path.join(__dirname, "..", filePath);

  if (fs.existsSync(fullPath)) {
    fs.unlink(fullPath, (err) => {
      if (err) console.error("Failed to delete old file:", err);
    });
  }
};

// 👇 NON-BREAKING EXPORT
module.exports = upload;
module.exports.deleteFileIfExists = deleteFileIfExists;
