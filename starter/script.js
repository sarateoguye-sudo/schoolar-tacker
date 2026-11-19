// Scholar Tracker starter website
// This file adds small interactive details to the page.

const yearElement = document.querySelector("#year");

if (yearElement) {
  yearElement.textContent = new Date().getFullYear();
}

console.log("Scholar Tracker starter website loaded.");